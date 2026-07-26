"""
services/agents/coordinator.py
AgentCoordinator for Phase 2.5 Multi-Agent Reasoning.
Drives planning and execution of ReasoningPlan across 5 roles.
Enforces shared context ownership, depends_on, conditions, revision caps, and cancellation checks.
"""

import logging
from typing import Dict, Any, List, Optional
from services.tools.models import (
    AgentRole, AgentStep, AgentStepStatus, ReasoningPlan, AgentResult, AgentInput, AgentOutput, ValidationOutcome
)
from services.agents.planner import PlannerAgent
from services.agents.research import ResearchAgent
from services.agents.tool import ToolAgent
from services.agents.critic import CriticAgent
from services.agents.synthesizer import SynthesizerAgent

logger = logging.getLogger(__name__)

# Configurable max revision cap (PROVISIONAL: hard cap = 1 retry)
MAX_REVISION_CAP = 1

# Strict Context Ownership Map: Context Key -> Owning Agent Role
CONTEXT_OWNERSHIP_MAP: Dict[str, AgentRole] = {
    "planner_output": AgentRole.PLANNER,
    "research_findings": AgentRole.RESEARCH,
    "tool_call_requests": AgentRole.RESEARCH,
    "tool_results": AgentRole.TOOL,
    "critic_evaluation": AgentRole.CRITIC,
    "revision_requested": AgentRole.CRITIC,
    "final_response": AgentRole.SYNTHESIZER,
    "memory_write_candidates": AgentRole.SYNTHESIZER,
}

# Immutable request fields set once at start
IMMUTABLE_REQUEST_FIELDS = {
    "request_id", "raw_command", "session_id", "source", "stt_confidence", "audio_quality"
}


class AgentCoordinatorResult:
    """Outcome container for AgentCoordinator execution."""
    def __init__(
        self,
        request_id: str,
        plan_id: str,
        outcome: ValidationOutcome,
        final_response: Optional[str],
        step_results: List[AgentResult],
        revision_count: int = 0
    ):
        self.request_id = request_id
        self.plan_id = plan_id
        self.outcome = outcome
        self.final_response = final_response
        self.step_results = step_results
        self.revision_count = revision_count


class AgentCoordinator:
    """
    Drives execution of multi-agent ReasoningPlan.
    """

    def __init__(self):
        self._agents = {
            AgentRole.PLANNER: PlannerAgent(),
            AgentRole.RESEARCH: ResearchAgent(),
            AgentRole.TOOL: ToolAgent(),
            AgentRole.CRITIC: CriticAgent(),
            AgentRole.SYNTHESIZER: SynthesizerAgent(),
        }
        self.cancelled_requests = set()

    def cancel_request(self, request_id: str):
        """Flags request_id as cancelled."""
        self.cancelled_requests.add(request_id)

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Safe dict lookup for condition evaluation without dynamic eval()."""
        if not condition:
            return True
        val = context.get(condition)
        if val is None:
            return False
        return bool(val)

    def _relevant_outputs_for(self, role: AgentRole, recorded_outcomes: Dict[str, AgentResult]) -> Dict[str, Any]:
        """
        Per-agent-role filter that determines which prior AgentOutputs each agent receives in AgentInput.previous_outputs.
        - Planner: receives NONE.
        - Research: receives Planner's plan ONLY.
        - Tool: receives Research findings ONLY.
        - Critic: receives Planner, Research, and Tool outputs (excludes raw conversation history).
        - Synthesizer: receives a compressed representation of all prior outputs (excluding raw reasoning fields).
        """
        filtered = {}
        if role == AgentRole.PLANNER:
            return {}
        elif role == AgentRole.RESEARCH:
            for s_id, s_res in recorded_outcomes.items():
                if s_res.agent_role == AgentRole.PLANNER:
                    filtered[s_id] = s_res.output
        elif role == AgentRole.TOOL:
            for s_id, s_res in recorded_outcomes.items():
                if s_res.agent_role == AgentRole.RESEARCH:
                    filtered[s_id] = s_res.output
        elif role == AgentRole.CRITIC:
            for s_id, s_res in recorded_outcomes.items():
                if s_res.agent_role in (AgentRole.PLANNER, AgentRole.RESEARCH, AgentRole.TOOL):
                    filtered[s_id] = s_res.output
        elif role == AgentRole.SYNTHESIZER:
            for s_id, s_res in recorded_outcomes.items():
                # Compressed representation: include output string / structured summary only, excluding raw reasoning
                val_str = str(s_res.output) if s_res.output else ""
                filtered[s_id] = val_str[:200]
        else:
            filtered = {s_id: s_res.output for s_id, s_res in recorded_outcomes.items()}

        return filtered

    def run(
        self,
        request_id: str,
        raw_command: str,
        *,
        session_id: str = "default_session",
        source: str = "voice",
        stt_confidence: float = 0.90,
        audio_quality: float = 1.0,
        executor_overrides: Optional[Dict[str, Any]] = None
    ) -> AgentCoordinatorResult:
        """Drives multi-agent reasoning pipeline execution."""

        # Speak initial acknowledgment via existing acknowledgment service pattern
        try:
            from services.acknowledgement_service import acknowledgement_service
            from services.speech_service import speech
            ack_msg = acknowledgement_service.generate(raw_command, is_question=True, use_web=True)
            speech.speak(ack_msg, request_id=request_id)
        except Exception as e:
            logger.debug(f"Acknowledgment speech skipped/errored: {e}")

        executor_overrides = executor_overrides or {}
        
        # Initialize Shared Context with immutable fields
        shared_context: Dict[str, Any] = {
            "request_id": request_id,
            "raw_command": raw_command,
            "session_id": session_id,
            "source": source,
            "stt_confidence": stt_confidence,
            "audio_quality": audio_quality,
        }

        # Determine routing decision & profile expansion via BrainRouter
        from services.brain.router import brain_router
        routing_decision = brain_router.route(raw_command)
        
        # Step 1: Planner Agent generates ReasoningPlan
        planner: PlannerAgent = self._agents[AgentRole.PLANNER]
        plan = planner.generate_plan(request_id, raw_command)
        
        # If routed via MULTI_AGENT or explicit profile, expand profile; default to plan's defined steps
        if routing_decision.route == "MULTI_AGENT":
            active_roles = brain_router.expand_profile(routing_decision.profile)
            steps_to_run = [s for s in plan.steps if s.agent_role in active_roles]
            if AgentRole.PLANNER in active_roles and not any(s.agent_role == AgentRole.PLANNER for s in steps_to_run):
                planner_step = AgentStep(step_id="step_planner", agent_role=AgentRole.PLANNER, params={})
                steps_to_run.insert(0, planner_step)
        else:
            steps_to_run = list(plan.steps)

        shared_context.update(plan.context)

        recorded_outcomes: Dict[str, AgentResult] = {}
        step_results: List[AgentResult] = []
        revision_count = 0
        has_success = False
        has_failure = False

        step_index = 0

        while step_index < len(steps_to_run):
            # Check cancellation between steps
            if request_id in self.cancelled_requests:
                logger.info(f"AgentCoordinator: Request {request_id} cancelled mid-chain.")
                return AgentCoordinatorResult(
                    request_id=request_id,
                    plan_id=plan.plan_id,
                    outcome=ValidationOutcome.FATAL_FAILURE,
                    final_response=None,
                    step_results=step_results,
                    revision_count=revision_count
                )

            step = steps_to_run[step_index]

            # 1. Dependency Enforcement
            if step.depends_on:
                dep_res = recorded_outcomes.get(step.depends_on)
                if not dep_res or not (dep_res.status == AgentStepStatus.SUCCESS and not dep_res.skipped):
                    logger.warning(f"AgentCoordinator: Step {step.step_id} skipped due to dependency failure ({step.depends_on})")
                    res = AgentResult(
                        agent_role=step.agent_role,
                        status=AgentStepStatus.SKIPPED,
                        skipped=True,
                        skip_reason=f"dependency_{step.depends_on}_not_successful",
                        step_id=step.step_id
                    )
                    has_failure = True
                    recorded_outcomes[step.step_id] = res
                    step_results.append(res)
                    step_index += 1
                    continue

            # 2. Condition Evaluation
            if step.condition and not self._evaluate_condition(step.condition, shared_context):
                logger.info(f"AgentCoordinator: Step {step.step_id} skipped due to condition false ({step.condition})")
                res = AgentResult(
                    agent_role=step.agent_role,
                    status=AgentStepStatus.SKIPPED,
                    skipped=True,
                    skip_reason=f"condition_{step.condition}_false",
                    step_id=step.step_id
                )
                recorded_outcomes[step.step_id] = res
                step_results.append(res)
                step_index += 1
                continue

            # 3. Execute Step Agent with PlannerCache lookup gate
            agent = self._agents[step.agent_role]
            step_params = dict(step.params)
            requires_memory = step.requires_memory
            override_key = step.step_id if step.step_id in executor_overrides else (step.agent_role.value if step.agent_role.value in executor_overrides else None)
            if override_key:
                override_dict = dict(executor_overrides[override_key])
                if "requires_memory" in override_dict:
                    requires_memory = override_dict.pop("requires_memory")
                step_params.update(override_dict)

            # Memory Opt-in Injection (Phase 2.6 Goal 4 & Phase 2.5c Part 1 Canonicalization)
            if requires_memory:
                from services.memory.memory_service import memory_service
                memory_dict = {
                    "user_facts": memory_service.get_all_facts(),
                    "session_space": memory_service.get_session_val("current_space", None)
                }
            else:
                memory_dict = {}

            # Construct standardized AgentInput with per-agent role filtered previous_outputs
            previous_outputs = self._relevant_outputs_for(step.agent_role, recorded_outcomes)
            agent_input = AgentInput(
                request=raw_command,
                shared_context=shared_context,
                memory=memory_dict,
                previous_outputs=previous_outputs,
                execution_constraints={}
            )
            setattr(agent_input, "step_id", step.step_id)

            # Planner Cache Pre-Invocation Lookup Gate
            from services.brain.planner_cache import planner_cache, PlannerCache
            cache_key = None
            cached_plan = None
            if step.agent_role == AgentRole.PLANNER:
                profile_name = routing_decision.profile.name if hasattr(routing_decision, "profile") and routing_decision.profile else "FULL_REASONING"
                cache_key = PlannerCache.make_key(raw_command, profile_name)
                cached_plan = planner_cache.get(cache_key)
                if cached_plan is not None:
                    logger.info(f"PlannerCache HIT for key {cache_key[:8]}... (Request: '{raw_command[:40]}')")

            try:
                from core.telemetry import pipeline_timer
                pipeline_timer.log_event(f"agent_step_start:{step.agent_role.value}")
                if cached_plan is not None:
                    res = AgentOutput(
                        agent_role=AgentRole.PLANNER,
                        status=AgentStepStatus.SUCCESS,
                        output=cached_plan,
                        structured_result=cached_plan,
                        context_writes={"execution_plan": cached_plan}
                    )
                else:
                    res = agent.run(agent_input, step_params)

                    # Post-contract-validation cache write for Planner
                    if step.agent_role == AgentRole.PLANNER and cache_key and res.status == AgentStepStatus.SUCCESS:
                        plan_obj = getattr(res, "structured_result", None) or getattr(res, "output", None)
                        if isinstance(plan_obj, ExecutionPlan) and getattr(plan_obj, "cacheable", True):
                            planner_cache.set(cache_key, plan_obj)

                pipeline_timer.log_event(f"agent_step_end:{step.agent_role.value}")
                res.step_id = step.step_id
            except Exception as ex:
                logger.error(f"AgentCoordinator: Error in agent {step.agent_role.value}: {ex}")
                res = AgentResult(
                    agent_role=step.agent_role,
                    status=AgentStepStatus.FAILED,
                    error=str(ex),
                    step_id=step.step_id
                )

            # 4. Context Ownership Validation
            if res.status == AgentStepStatus.SUCCESS and res.context_writes:
                for key, val in list(res.context_writes.items()):
                    if key in IMMUTABLE_REQUEST_FIELDS:
                        logger.error(f"AgentCoordinator: Agent {step.agent_role.value} attempted to overwrite immutable field '{key}'! Rejected.")
                        res.status = AgentStepStatus.FAILED
                        res.error = f"unauthorized_write_to_immutable_key_{key}"
                        break

                    owner = CONTEXT_OWNERSHIP_MAP.get(key)
                    if owner is not None and owner != step.agent_role:
                        logger.error(f"AgentCoordinator: Agent {step.agent_role.value} attempted to write key '{key}' owned by {owner.value}! Rejected.")
                        res.status = AgentStepStatus.FAILED
                        res.error = f"unauthorized_context_write_{key}_by_{step.agent_role.value}"
                        break
                    else:
                        shared_context[key] = val

            recorded_outcomes[step.step_id] = res
            step_results.append(res)

            if res.status == AgentStepStatus.SUCCESS:
                has_success = True
            else:
                has_failure = True

            # Handle Revision Request from Critic
            if step.agent_role == AgentRole.CRITIC and shared_context.get("revision_requested"):
                if revision_count < MAX_REVISION_CAP:
                    revision_count += 1
                    logger.info(f"AgentCoordinator: Critic requested revision. Rerunning Research (revision #{revision_count}).")
                    shared_context["revision_requested"] = False
                    # Insert fresh research & critic steps into queue
                    steps_to_run.insert(step_index + 1, AgentStep(
                        step_id=f"step_research_rev{revision_count}",
                        agent_role=AgentRole.RESEARCH,
                        params={"query": raw_command}
                    ))
                    steps_to_run.insert(step_index + 2, AgentStep(
                        step_id=f"step_critic_rev{revision_count}",
                        agent_role=AgentRole.CRITIC,
                        depends_on=f"step_research_rev{revision_count}",
                        params={}
                    ))
                else:
                    logger.warning(f"AgentCoordinator: Revision cap reached ({MAX_REVISION_CAP}). Ignoring further revision requests.")

            step_index += 1

        # Classify Plan Outcome (matching TEL classification)
        if not has_failure:
            outcome = ValidationOutcome.COMPLETE_SUCCESS
        elif has_success and has_failure:
            outcome = ValidationOutcome.PARTIAL_SUCCESS
        else:
            outcome = ValidationOutcome.FATAL_FAILURE

        final_response = shared_context.get("final_response")

        return AgentCoordinatorResult(
            request_id=request_id,
            plan_id=plan.plan_id,
            outcome=outcome,
            final_response=final_response,
            step_results=step_results,
            revision_count=revision_count
        )


agent_coordinator = AgentCoordinator()
