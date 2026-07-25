"""
services/agents/prompt_templates.py
AgentPromptTemplate subclasses for Phase 2.7 Task 2 Prompt Optimization.
Provides explicit SYSTEM / USER REQUEST / AVAILABLE CONTEXT / MEMORY / TASK / OUTPUT FORMAT sections.
"""

from typing import Dict, Any, Optional
from services.agents.shared_prompt_fragments import PERSONA_INSTRUCTION, FORMATTING_RULES, SAFETY_REMINDERS
from services.conversation.conversation_summary import ConversationSummary


class AgentPromptTemplate:
    """Base prompt template class enforcing section formatting."""

    def build_prompt(
        self,
        user_request: str,
        shared_context: Dict[str, Any],
        memory: Dict[str, Any],
        previous_outputs: Dict[str, Any],
        execution_metadata: Dict[str, Any]
    ) -> Dict[str, str]:
        """Returns structured dictionary of sections + final formatted prompt string."""
        sys_section = f"--- SYSTEM ---\n{PERSONA_INSTRUCTION}\n{SAFETY_REMINDERS}"
        
        history = shared_context.get("history", [])
        conv_hist = ConversationSummary.get_capped_summary(history)
        hist_section = f"--- CONVERSATION HISTORY ---\n{conv_hist}" if conv_hist else ""

        user_section = f"--- USER REQUEST ---\n{user_request}"
        
        ctx_lines = [f"{k}: {v}" for k, v in previous_outputs.items() if v]
        ctx_section = f"--- AVAILABLE CONTEXT ---\n" + "\n".join(ctx_lines) if ctx_lines else ""

        mem_facts = memory.get("user_facts", [])
        mem_section = f"--- MEMORY ---\nUser Facts: {', '.join(mem_facts)}" if mem_facts else ""

        task_section = self._build_task_section(user_request)
        out_section = f"--- OUTPUT FORMAT ---\n{FORMATTING_RULES}"

        full_prompt = "\n\n".join(
            sec for sec in [sys_section, hist_section, user_section, ctx_section, mem_section, task_section, out_section] if sec
        )

        return {
            "sys_inst": sys_section,
            "conv_hist": hist_section,
            "shared_ctx": ctx_section,
            "memory_str": mem_section,
            "exec_meta": f"Constraints: {execution_metadata}",
            "user_req": user_section,
            "full_prompt": full_prompt
        }

    def _build_task_section(self, user_request: str) -> str:
        raise NotImplementedError


class PlannerPromptTemplate(AgentPromptTemplate):
    def _build_task_section(self, user_request: str) -> str:
        return f"--- TASK ---\nDecompose the user request into high-level sub-goals for execution planning. Do not execute."


class ResearchPromptTemplate(AgentPromptTemplate):
    def _build_task_section(self, user_request: str) -> str:
        return f"--- TASK ---\nGather background context and research findings required to address the user request."


class CriticPromptTemplate(AgentPromptTemplate):
    def _build_task_section(self, user_request: str) -> str:
        return f"--- TASK ---\nEvaluate prior research findings and tool execution outputs for completeness and accuracy."


class SynthesizerPromptTemplate(AgentPromptTemplate):
    def _build_task_section(self, user_request: str) -> str:
        return f"--- TASK ---\nSynthesize a clear, conversational final answer for the user based on all prior context and outputs."
