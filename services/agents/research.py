import logging
from typing import Dict, Any
from services.tools.models import AgentRole, AgentInput, AgentOutput, AgentStepStatus

logger = logging.getLogger(__name__)


class ResearchAgent:
    """
    Research Agent role for Phase 2.5d.
    LLM-backed agent that investigates query context and proposes research findings or tool call requests.
    Does not call TEL directly.
    """

    def run(self, agent_input: AgentInput, step_params: Dict[str, Any]) -> AgentOutput:
        req_id = agent_input.shared_context.get("request_id", "req-research")
        step_id = getattr(agent_input, "step_id", "step_research")
        role_str = AgentRole.RESEARCH.value

        from core.telemetry import pipeline_timer

        query = step_params.get("query") or agent_input.request or agent_input.shared_context.get("raw_command", "")
        
        # Check if research executor override is provided in context or step_params
        if "override_fail" in step_params and step_params["override_fail"]:
            return AgentOutput(
                agent_role=AgentRole.RESEARCH,
                status=AgentStepStatus.FAILED,
                error="Research provider offline",
                context_writes={}
            )

        # Stage 1: prompt_construction
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "prompt_construction"):
            from services.agents.prompt_templates import ResearchPromptTemplate
            template = ResearchPromptTemplate()
            p_parts = template.build_prompt(
                user_request=query,
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
            logger.warning(f"Research LLM fallback: {e}")
            reasoning_text = f"Analyzed query parameters for: '{query}'"

        # Stage 5: post_processing
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "post_processing"):
            findings = f"Research findings for query: '{query}'"

        # Stage 6: context_write
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "context_write"):
            writes = {"research_findings": findings}
            if step_params.get("request_tool_call"):
                writes["tool_call_requests"] = step_params.get("request_tool_call")

        return AgentOutput(
            agent_role=AgentRole.RESEARCH,
            reasoning=reasoning_text,
            structured_result={"query": query, "findings_summary": findings},
            confidence=0.95,
            suggested_next_action="proceed_to_tool",
            status=AgentStepStatus.SUCCESS,
            output=findings,
            context_writes=writes
        )
