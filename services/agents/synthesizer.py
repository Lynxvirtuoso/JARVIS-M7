import logging
from typing import Dict, Any
from services.tools.models import AgentRole, AgentInput, AgentOutput, AgentStepStatus

logger = logging.getLogger(__name__)


class SynthesizerAgent:
    """
    Synthesizer Agent role for Phase 2.5d.
    Aggregates research_findings, tool_results, and critic_evaluation from shared_context,
    and synthesizes a coherent final response through LLM streaming / SentenceBuffer / streaming_tts_queue pipeline.
    """

    def run(self, agent_input: AgentInput, step_params: Dict[str, Any]) -> AgentOutput:
        req_id = agent_input.shared_context.get("request_id", "req-synth")
        step_id = getattr(agent_input, "step_id", "step_synthesizer")
        role_str = AgentRole.SYNTHESIZER.value

        from core.telemetry import pipeline_timer

        shared = agent_input.shared_context
        research = shared.get("research_findings", "")
        tools = shared.get("tool_results", "")
        critic = shared.get("critic_evaluation", "")
        raw_cmd = agent_input.request or shared.get("raw_command", "")
        request_id = shared.get("request_id", "req-synth")

        # Stage 1: prompt_construction
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "prompt_construction"):
            from services.agents.prompt_templates import SynthesizerPromptTemplate
            template = SynthesizerPromptTemplate()
            p_parts = template.build_prompt(
                user_request=raw_cmd,
                shared_context=agent_input.shared_context,
                memory=agent_input.memory,
                previous_outputs=agent_input.previous_outputs,
                execution_metadata=agent_input.execution_constraints
            )
            synthesis_prompt = p_parts["full_prompt"]
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

        first_token_seen = False

        # Stage 2: provider_request_sent marker
        pipeline_timer.log_stage_event(req_id, step_id, role_str, "provider_request_sent")

        try:
            from core.brain import brain
            from services.tts.sentence_buffer import SentenceBuffer
            from services.tts.streaming_tts_queue import streaming_tts_queue
            from services.speech_service import speech

            sentence_buffer = SentenceBuffer(first_sentence_minimum_chars=15)
            full_response_chunks = []

            logger.info(f"SynthesizerAgent: Streaming LLM synthesis for request {request_id}...")
            streaming_tts_queue.start_new_request(request_id)

            for token in brain.think_stream(synthesis_prompt):
                if isinstance(token, str):
                    if not first_token_seen:
                        first_token_seen = True
                        # Stage 3: first_token_received marker
                        pipeline_timer.log_stage_event(req_id, step_id, role_str, "first_token_received")
                    full_response_chunks.append(token)
                    sentences = sentence_buffer.add_chunk(token)
                    for sentence in sentences:
                        streaming_tts_queue.enqueue_sentence(request_id, sentence)

            # Stage 4: last_token_received marker
            pipeline_timer.log_stage_event(req_id, step_id, role_str, "last_token_received")

            remaining_sentence = sentence_buffer.flush()
            if remaining_sentence:
                streaming_tts_queue.enqueue_sentence(request_id, remaining_sentence)

            final_text = "".join(full_response_chunks).strip()
            if not final_text:
                final_text = f"Based on research and tool results: {research} | {tools}"

        except Exception as e:
            logger.warning(f"SynthesizerAgent LLM streaming fallback: {e}")
            final_text = f"Synthesized findings for '{raw_cmd}': {research} | {tools}"

        # Stage 5: post_processing
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "post_processing"):
            memory_write_candidates = step_params.get("write_candidates", [])
            context_writes = {"final_response": final_text}
            if memory_write_candidates:
                context_writes["memory_write_candidates"] = list(memory_write_candidates)

        # Stage 6: context_write
        with pipeline_timer.timed_stage(req_id, step_id, role_str, "context_write"):
            pass

        return AgentOutput(
            agent_role=AgentRole.SYNTHESIZER,
            reasoning=f"Synthesized final response for '{raw_cmd}'.",
            structured_result={"final_response": final_text},
            confidence=0.99,
            suggested_next_action="complete",
            status=AgentStepStatus.SUCCESS,
            output=final_text,
            context_writes=context_writes
        )
