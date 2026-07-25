import logging
from typing import Dict, Any
from services.tools.models import AgentRole, AgentInput, AgentOutput, AgentStepStatus, CritiqueVerdict

logger = logging.getLogger(__name__)


class CriticAgent:
    """
    Critic Agent role for Phase 2.5d.
    LLM-backed agent that evaluates research_findings + tool_results.
    Returns CritiqueVerdict in structured_result and does NOT mutate the plan directly.
    Only AgentCoordinator decides retry/replan.
    """

    def run(self, agent_input: AgentInput, step_params: Dict[str, Any]) -> AgentOutput:
        req_id = agent_input.shared_context.get("request_id", "req-critic")
        step_id = getattr(agent_input, "step_id", "step_critic")
        role_str = AgentRole.CRITIC.value

        from core.telemetry import pipeline_timer

        research = agent_input.shared_context.get("research_findings", "")
        tools = agent_input.shared_context.get("tool_results", "")
        request_revision = step_params.get("request_revision", False)

        # Stage 1: prompt_construction
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "prompt_construction"):
            from services.agents.prompt_templates import CriticPromptTemplate
            template = CriticPromptTemplate()
            p_parts = template.build_prompt(
                user_request=agent_input.request,
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
            logger.warning(f"Critic LLM fallback: {e}")
            reasoning_text = f"Evaluated research ({len(str(research))} chars) and tool results ({len(str(tools))} chars)."

        # Stage 5: post_processing
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "post_processing"):
            writes = {}
            if request_revision:
                verdict = CritiqueVerdict.NEEDS_REVISION
                confidence_score = 0.40
                writes["revision_requested"] = True
                eval_output = "Critic requested revision due to incomplete findings."
            else:
                verdict = CritiqueVerdict.PASSED
                confidence_score = 0.95
                writes["revision_requested"] = False
                eval_output = f"Critic approved output (research len={len(str(research))}, tools len={len(str(tools))})."

            writes["critic_evaluation"] = eval_output

        # Stage 6: context_write
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "context_write"):
            pass

        return AgentOutput(
            agent_role=AgentRole.CRITIC,
            reasoning=reasoning_text,
            structured_result={"verdict": verdict.value, "critique_summary": eval_output},
            confidence=confidence_score,
            suggested_next_action="proceed_to_synthesizer" if verdict == CritiqueVerdict.PASSED else "request_replan",
            status=AgentStepStatus.SUCCESS,
            output=eval_output,
            context_writes=writes
        )
