import logging
import uuid
from typing import Dict, Any, List
from services.tools.models import (
    AgentRole, AgentStep, ReasoningPlan, AgentInput, AgentOutput, AgentStepStatus
)

logger = logging.getLogger(__name__)


class PlannerContractViolation(RuntimeError):
    pass


class PlannerAgent:
    """
    Planner Agent role for Phase 2.5d.
    Generates execution plans and validates that plans contain strictly decomposition steps,
    rejecting any plan containing direct tool_call payloads or response outputs.
    """

    def generate_plan(self, request_id: str, raw_command: str, params: Dict[str, Any] = None) -> ReasoningPlan:
        params = params or {}
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"

        from services.memory.memory_service import memory_service
        user_facts = memory_service.get_all_facts()
        current_space = memory_service.get_session_val("current_space", None)

        steps = [
            AgentStep(
                step_id="step_research",
                agent_role=AgentRole.RESEARCH,
                params={"query": raw_command}
            ),
            AgentStep(
                step_id="step_tool",
                agent_role=AgentRole.TOOL,
                depends_on="step_research",
                params={}
            ),
            AgentStep(
                step_id="step_critic",
                agent_role=AgentRole.CRITIC,
                depends_on="step_tool",
                params={}
            ),
            AgentStep(
                step_id="step_synthesizer",
                agent_role=AgentRole.SYNTHESIZER,
                depends_on="step_critic",
                params={}
            )
        ]

        return ReasoningPlan(
            plan_id=plan_id,
            request_id=request_id,
            steps=steps,
            context={"planner_output": f"Plan generated for '{raw_command}'"}
        )

    def run(self, agent_input: AgentInput, step_params: Dict[str, Any]) -> AgentOutput:
        """
        Executes Planner reasoning with strict contract validation and latency profiling.
        Rejects plan if step_params or input attempts to embed a direct 'tool_call' or 'response' payload.
        """
        req_id = agent_input.shared_context.get("request_id", "req-planner")
        step_id = getattr(agent_input, "step_id", "step_planner")
        role_str = AgentRole.PLANNER.value

        from core.telemetry import pipeline_timer

        req_text = agent_input.request
        
        # Hard contract validation: Reject direct tool_call or response payloads
        if "tool_call" in step_params or "response" in step_params or "tool_call" in agent_input.execution_constraints:
            raise PlannerContractViolation("Planner contract violation: direct tool_call or response payload in plan definition!")

        # Stage 1: prompt_construction
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "prompt_construction"):
            from services.agents.prompt_templates import PlannerPromptTemplate
            template = PlannerPromptTemplate()
            p_parts = template.build_prompt(
                user_request=req_text,
                shared_context=agent_input.shared_context,
                memory=agent_input.memory,
                previous_outputs=agent_input.previous_outputs,
                execution_metadata=agent_input.execution_constraints
            )
            prompt = p_parts["full_prompt"]
            pipeline_timer.log_prompt_token_audit(
                request_id=req_id,
                step_id=step_id,
                agent_role=role_str,
                sys_inst=p_parts["sys_inst"],
                conv_hist=p_parts["conv_hist"],
                shared_ctx=p_parts["shared_ctx"],
                memory_str=p_parts["memory_str"],
                exec_meta=p_parts["exec_meta"],
                user_req=p_parts["user_req"]
            )

        reasoning_chunks = []
        first_token_seen = False
        
        # Stage 2: provider_request_sent marker
        pipeline_timer.log_stage_event(req_id, step_id, role_str, "provider_request_sent")

        try:
            from core.brain import brain
            for token in brain.think_stream(prompt):
                if isinstance(token, str):
                    if not first_token_seen:
                        first_token_seen = True
                        # Stage 3: first_token_received marker
                        pipeline_timer.log_stage_event(req_id, step_id, role_str, "first_token_received")
                    reasoning_chunks.append(token)
            
            # Stage 4: last_token_received marker
            pipeline_timer.log_stage_event(req_id, step_id, role_str, "last_token_received")
            reasoning_text = "".join(reasoning_chunks).strip()
        except Exception as e:
            logger.warning(f"Planner LLM fallback: {e}")
            reasoning_text = f"Decomposed request: {req_text}"

        # Stage 5: post_processing
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "post_processing"):
            plan_desc = f"Planned execution strategy for: '{req_text}'"

        # Stage 6: context_write
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "context_write"):
            writes = {"planner_output": plan_desc}

        return AgentOutput(
            agent_role=AgentRole.PLANNER,
            reasoning=reasoning_text,
            structured_result={"plan_description": plan_desc},
            confidence=0.98,
            suggested_next_action="proceed_to_research",
            status=AgentStepStatus.SUCCESS,
            output=plan_desc,
            context_writes=writes
        )
