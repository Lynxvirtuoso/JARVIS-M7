from typing import Dict, Any
from services.tools.models import AgentRole, AgentInput, AgentOutput, AgentStepStatus


class ToolAgent:
    """
    Tool Agent role for Phase 2.5d.
    Deterministic tool dispatcher that translates plan steps into ToolCalls and delegates to TEL + TrustGate.
    Makes ZERO LLM calls.
    """

    def run(self, agent_input: AgentInput, step_params: Dict[str, Any]) -> AgentOutput:
        req_id = agent_input.shared_context.get("request_id", "req-tool")
        step_id = getattr(agent_input, "step_id", "step_tool")
        role_str = AgentRole.TOOL.value

        from core.telemetry import pipeline_timer

        if step_params.get("override_fail"):
            return AgentOutput(
                agent_role=AgentRole.TOOL,
                reasoning="Deterministic execution override failed.",
                confidence=0.0,
                status=AgentStepStatus.FAILED,
                error="Tool execution service failure",
                context_writes={}
            )

        with pipeline_timer.timed_stage(req_id, step_id, role_str, "prompt_construction"):
            tool_requests = agent_input.shared_context.get("tool_call_requests") or step_params.get("tool_requests")

        with pipeline_timer.timed_stage(req_id, step_id, role_str, "post_processing"):
            if tool_requests:
                from services.tools.tool_execution_layer import tool_execution_layer
                from services.skills.orchestrator import skill_orchestrator
                
                if isinstance(tool_requests, str):
                    plan = skill_orchestrator.plan_request(agent_input.shared_context.get("request_id", "req-agent"), tool_requests)
                    tel_res = tool_execution_layer.execute_plan(plan)
                    output = f"TEL Execution: {tel_res.outcome.value} - {tel_res.spoken_summary}"
                else:
                    output = f"Executed tool requests: {tool_requests}"
            else:
                output = "No tool execution requested."

        with pipeline_timer.timed_stage(req_id, step_id, role_str, "context_write"):
            writes = {"tool_results": output}

        return AgentOutput(
            agent_role=AgentRole.TOOL,
            reasoning="Deterministic execution of requested tools via TEL.",
            structured_result={"tool_requests": tool_requests, "execution_summary": output},
            confidence=1.0,
            suggested_next_action="proceed_to_critic",
            status=AgentStepStatus.SUCCESS,
            output=output,
            context_writes=writes
        )
