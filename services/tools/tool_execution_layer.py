"""
services/tools/tool_execution_layer.py
Phase 2.3 Tool Execution Layer (TEL) for JARVIS M7.
Executes multi-step ExecutionPlans sequentially under a single request_id,
evaluates TrustGate confirmation plans, checks cancellation between steps,
validates outcomes, and streams spoken explanations for non-complete outcomes.
"""

import logging
import time
from typing import Optional, Dict, Any, List

from core.trust_gate import TrustGate
from services.tools.models import (
    ExecutionPlan,
    ToolStep,
    StepResult,
    ValidationOutcome,
    PlanConfirmation,
    PlanExecutionResult,
)
from services.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class ToolExecutionLayer:
    """
    Multi-step tool execution coordinator sitting between Brain Router and Skill/Tool execution.
    """

    def __init__(self):
        self._cancelled_requests: set = set()

    def request_cancel(self, request_id: str) -> None:
        """Flags a request_id as cancelled for TEL execution."""
        self._cancelled_requests.add(request_id)
        logger.info(f"[TEL] Cancellation registered for request_id: {request_id}")

    def is_cancelled(self, request_id: str) -> bool:
        """Checks if request_id has been cancelled."""
        return request_id in self._cancelled_requests

    def execute_plan(
        self,
        plan: ExecutionPlan,
        executor_override: Optional[Dict[str, Any]] = None,
    ) -> PlanExecutionResult:
        """
        Executes an ExecutionPlan sequentially under plan.request_id.
        """
        req_id = plan.request_id
        logger.info(f"[TEL] Starting plan execution '{plan.plan_id}' for req_id: {req_id} ({len(plan.steps)} steps)")

        # 1. TrustGate Plan Evaluation
        confirmation_plan: PlanConfirmation = TrustGate.evaluate_plan(plan)
        if confirmation_plan.requires_confirmation:
            logger.info(
                f"[TEL] Plan '{plan.plan_id}' requires TrustGate confirmation: "
                f"{confirmation_plan.confirmations_required}"
            )

        step_results: List[StepResult] = []
        recorded_outcomes: Dict[str, StepResult] = {}
        has_failure = False
        has_success = False

        # 2. Sequential Step Execution under single request_id
        for step in plan.steps:
            # Check cancellation pipeline prior to step execution
            if self.is_cancelled(req_id):
                logger.warning(f"[TEL] Request {req_id} cancelled mid-chain before step: {step.step_id}")
                res = StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    error="Cancelled by user/system",
                )
                step_results.append(res)
                recorded_outcomes[step.step_id] = res
                has_failure = True
                break

            # 2a. depends_on Enforcement
            if step.depends_on:
                dep_res = recorded_outcomes.get(step.depends_on)
                if not dep_res or not dep_res.success or dep_res.skipped:
                    logger.warning(
                        f"[TEL] Step {step.step_id} skipped due to failed/skipped dependency: {step.depends_on}"
                    )
                    res = StepResult(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        skipped=True,
                        skip_reason=f"dependency_{step.depends_on}_not_successful",
                    )
                    step_results.append(res)
                    recorded_outcomes[step.step_id] = res
                    has_failure = True
                    continue

            # 2b. condition Evaluation
            if step.condition and not self._evaluate_condition(step.condition, plan.context):
                logger.info(
                    f"[TEL] Step {step.step_id} skipped: condition '{step.condition}' evaluated False"
                )
                res = StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=True,  # Skipped due to False condition is intentional non-execution
                    skipped=True,
                    skip_reason=f"condition_{step.condition}_false",
                )
                step_results.append(res)
                recorded_outcomes[step.step_id] = res
                continue

            # Execute step handler
            res = self._execute_step(step, executor_override)
            step_results.append(res)
            recorded_outcomes[step.step_id] = res

            if res.success and not res.skipped:
                has_success = True
            elif not res.success and not res.skipped:
                has_failure = True

        # 3. Validation Outcome Classification
        outcome = self._classify_outcome(step_results, has_success, has_failure, self.is_cancelled(req_id))

        # 4. Spoken Explanation Generation
        spoken_summary = self._generate_spoken_explanation(plan, step_results, outcome)

        logger.info(f"[TEL] Completed plan '{plan.plan_id}' | Outcome: {outcome.value} | Spoken: '{spoken_summary}'")

        return PlanExecutionResult(
            plan_id=plan.plan_id,
            request_id=req_id,
            outcome=outcome,
            step_results=step_results,
            spoken_summary=spoken_summary,
        )

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """
        Safely evaluates a condition against keys in plan.context.
        Performs a boolean lookup without dynamic eval().
        """
        val = context.get(condition, False)
        return bool(val)

    def _execute_step(
        self,
        step: ToolStep,
        executor_override: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """Executes a single step."""
        tool_meta = tool_registry.get_metadata(step.tool_name)
        if not tool_meta:
            logger.error(f"[TEL] Unknown tool: {step.tool_name}")
            return StepResult(step_id=step.step_id, tool_name=step.tool_name, success=False, error=f"Unknown tool: {step.tool_name}")

        handler = tool_registry.get_handler(step.tool_name)
        if executor_override and step.step_id in executor_override:
            handler = executor_override[step.step_id]

        if handler:
            try:
                out = handler(step.params)
                return StepResult(step_id=step.step_id, tool_name=step.tool_name, success=True, output=out)
            except Exception as e:
                logger.error(f"[TEL] Error executing step {step.step_id}: {e}", exc_info=True)
                return StepResult(step_id=step.step_id, tool_name=step.tool_name, success=False, error=str(e))
        else:
            # Default simulated successful execution if no custom handler bound
            return StepResult(step_id=step.step_id, tool_name=step.tool_name, success=True, output=f"Executed {step.action}")

    def _classify_outcome(
        self,
        step_results: List[StepResult],
        has_success: bool,
        has_failure: bool,
        is_cancelled: bool,
    ) -> ValidationOutcome:
        """Classifies net outcome of execution."""
        if is_cancelled:
            return ValidationOutcome.FATAL_FAILURE
        if not has_failure:
            return ValidationOutcome.COMPLETE_SUCCESS
        if has_success and has_failure:
            return ValidationOutcome.PARTIAL_SUCCESS
        return ValidationOutcome.FATAL_FAILURE

    def _generate_spoken_explanation(
        self,
        plan: ExecutionPlan,
        step_results: List[StepResult],
        outcome: ValidationOutcome,
    ) -> str:
        """Generates clear spoken feedback for the user."""
        skipped_dep_steps = [r for r in step_results if r.skipped and r.skip_reason and "dependency_" in r.skip_reason]
        if skipped_dep_steps:
            skip_step = skipped_dep_steps[0]
            dep_id = skip_step.skip_reason.replace("dependency_", "").replace("_not_successful", "")
            return f"Step {skip_step.tool_name} was skipped because its dependency {dep_id} failed, Sir."

        skipped_condition_steps = [r for r in step_results if r.skipped and r.skip_reason and "condition_" in r.skip_reason]
        if skipped_condition_steps:
            skip_step = skipped_condition_steps[0]
            cond_name = skip_step.skip_reason.replace("condition_", "").replace("_false", "")
            if cond_name == "is_free_after_1700":
                return f"Since you are not free after 5 PM, I did not set the reminder, Sir."
            return f"Condition {cond_name} evaluated false, so I skipped {skip_step.tool_name}, Sir."

        if outcome == ValidationOutcome.COMPLETE_SUCCESS:
            return f"Successfully executed all {len(step_results)} steps, Sir."

        if outcome == ValidationOutcome.PARTIAL_SUCCESS:
            successful_steps = [r.tool_name for r in step_results if r.success and not r.skipped]
            failed_steps = [r.tool_name for r in step_results if not r.success]
            succ_str = ", ".join(successful_steps)
            fail_str = ", ".join(failed_steps)
            return f"I completed steps for {succ_str}, but failed to complete {fail_str}, Sir."

        if outcome == ValidationOutcome.FATAL_FAILURE:
            if self.is_cancelled(plan.request_id):
                return "Task execution was cancelled, Sir."
            return "I encountered an error and could not complete the requested task, Sir."

        return "Task processing completed with warnings, Sir."


# Global TEL instance
tool_execution_layer = ToolExecutionLayer()
