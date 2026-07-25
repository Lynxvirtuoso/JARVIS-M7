"""
services/skills/orchestrator.py
Phase 2.4 Skill Orchestrator for JARVIS M7.
Planning-only component sitting between BrainRouter and ToolExecutionLayer.
Determines multi-skill participating steps, dependencies (depends_on),
conditions, and shared context without executing code or managing state.
"""

import logging
import uuid
from typing import Optional, Dict, Any, List

from services.tools.models import ExecutionPlan, ToolStep

logger = logging.getLogger(__name__)


class SkillOrchestrator:
    """
    Planning-only multi-skill orchestration component.
    """

    def plan_request(self, request_id: str, command: str) -> Optional[ExecutionPlan]:
        """
        Analyzes command and returns an ExecutionPlan if multi-skill orchestration is needed.
        Returns None for single-skill requests to preserve existing registry matching unchanged.
        """
        cmd_clean = command.strip().lower()

        # 1. Single-Skill Bypass (Zero Regression)
        if not self._is_multi_skill_command(cmd_clean):
            logger.debug(f"[SKILL_ORCHESTRATOR] Single-skill request '{command}' -> Bypass to existing registry.")
            return None

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan = ExecutionPlan(plan_id=plan_id, request_id=request_id)

        # 2. Sequential Multi-Skill Scenario
        # Example: "check my calendar, then play my focus playlist"
        if "then play" in cmd_clean or ("check my calendar" in cmd_clean and "play" in cmd_clean):
            logger.info(f"[SKILL_ORCHESTRATOR] Planning Sequential Multi-Skill: CalendarSkill -> MediaSkill")
            s1 = ToolStep(step_id="step_1", tool_name="calendar_tool", action="check_calendar")
            s2 = ToolStep(step_id="step_2", tool_name="media_tool", action="play_playlist", depends_on="step_1", params={"playlist": "focus playlist"})
            plan.steps = [s1, s2]
            plan.metadata["pattern"] = "sequential"
            return plan

        # 3. Conditional Multi-Skill Scenario
        # Example: "if I'm free after 5pm, remind me to call John"
        if cmd_clean.startswith("if ") or "if i'm free" in cmd_clean:
            logger.info(f"[SKILL_ORCHESTRATOR] Planning Conditional Multi-Skill: CalendarSkill -> ReminderSkill")
            s1 = ToolStep(step_id="step_1", tool_name="calendar_tool", action="check_free_time", params={"time_after": "17:00"})
            s2 = ToolStep(step_id="step_2", tool_name="reminder_tool", action="set_reminder", depends_on="step_1", condition="is_free_after_1700", params={"text": "Call John"})
            plan.steps = [s1, s2]
            plan.metadata["pattern"] = "conditional"
            return plan

        # 4. Data Handoff Multi-Skill Scenario
        # Example: "find today's meeting notes and summarize them"
        if "summarize" in cmd_clean and ("notes" in cmd_clean or "file" in cmd_clean or "find" in cmd_clean):
            logger.info(f"[SKILL_ORCHESTRATOR] Planning Data-Handoff Multi-Skill: FileSkill -> LLM Summarizer")
            s1 = ToolStep(step_id="step_1", tool_name="file_system", action="find_file", params={"query": "today's meeting notes"})
            s2 = ToolStep(step_id="step_2", tool_name="llm_summarizer", action="summarize_content", depends_on="step_1", params={"input_context_key": "meeting_notes_content"})
            plan.steps = [s1, s2]
            plan.metadata["pattern"] = "data_handoff"
            plan.context["meeting_notes_content"] = "Initial empty buffer for file content handoff"
            return plan

        logger.debug(f"[SKILL_ORCHESTRATOR] No multi-skill pattern matched for: '{command}'")
        return None

    def _is_multi_skill_command(self, cmd_clean: str) -> bool:
        """Determines if a command requires multi-skill coordination."""
        multi_keywords = [", then ", " then ", "if i'm free", "and summarize", "find "]
        return any(kw in cmd_clean for kw in multi_keywords) and (" and " in cmd_clean or " then " in cmd_clean or cmd_clean.startswith("if "))


# Global instance
skill_orchestrator = SkillOrchestrator()
