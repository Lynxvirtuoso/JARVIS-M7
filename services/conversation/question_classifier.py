"""
services/conversation/question_classifier.py
Phase 2.5b Question Classifier for JARVIS M7.
Single authoritative module for classifying user input metadata without making routing decisions.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ClassificationResult:
    question_type: str          # "wh_question", "aux_question", "info_request", "statement", "command"
    is_conversational: bool
    requires_tools: bool
    estimated_complexity: str   # "LOW" | "MEDIUM" | "HIGH"
    candidate_skills: List[str] = field(default_factory=list)
    candidate_tools: List[str] = field(default_factory=list)
    routing_hints: Dict[str, Any] = field(default_factory=dict)


class QuestionClassifier:
    """
    Pure-function classifier of transcript text.
    Produces metadata (ClassificationResult) only. NEVER makes routing or execution decisions.
    """

    WH_PATTERN = r"^(who|what|when|where|why|how)s?\b"
    AUX_PATTERN = r"^(is|are|was|were|did|does|do|can|could|will|would|have|has|had|should|must|may|might)\b"
    INFO_PATTERN = r"^(search|find|tell\s+me|explain|google)\b"
    ACTION_VERBS = ["open", "close", "launch", "start", "stop", "kill", "exit", "sleep"]

    def classify(self, text: str) -> ClassificationResult:
        if not text or not text.strip():
            return ClassificationResult(
                question_type="statement",
                is_conversational=False,
                requires_tools=False,
                estimated_complexity="LOW",
                candidate_skills=[],
                candidate_tools=[],
                routing_hints={"empty_input": True}
            )

        cmd_clean = re.sub(r"[.,!-;:'\"]+", "", text).lower().strip()

        # Check question patterns
        is_wh = bool(re.search(self.WH_PATTERN, cmd_clean))
        is_aux = bool(re.search(self.AUX_PATTERN, cmd_clean))
        is_info = bool(re.search(self.INFO_PATTERN, cmd_clean))

        is_conversational = is_wh or is_aux or is_info

        if is_wh:
            q_type = "wh_question"
        elif is_aux:
            q_type = "aux_question"
        elif is_info:
            q_type = "info_request"
        else:
            q_type = "command" if any(re.search(rf"\b{re.escape(v)}\b", cmd_clean) for v in self.ACTION_VERBS) else "statement"

        # Multi-intent / multi-step detection
        has_multi_intent = any(marker in cmd_clean for marker in [" and ", " then ", " if "])
        has_action = any(re.search(rf"\b{re.escape(verb)}\b", cmd_clean) for verb in self.ACTION_VERBS)
        
        # Skill / Tool candidate detection
        candidate_skills = []
        candidate_tools = []
        if any(kw in cmd_clean for kw in ["calendar", "meeting", "appointment", "schedule", "free", "busy"]):
            candidate_skills.append("Calendar")
            candidate_tools.append("calendar_tool")
        if any(kw in cmd_clean for kw in ["remind", "reminder", "alarm"]):
            candidate_skills.append("Reminder")
            candidate_tools.append("reminder_tool")
        if any(kw in cmd_clean for kw in ["music", "play", "playlist", "song"]):
            candidate_skills.append("Media")
            candidate_tools.append("media_tool")
        if any(kw in cmd_clean for kw in ["weather", "temperature", "forecast"]):
            candidate_skills.append("Weather")
            candidate_tools.append("weather_tool")
        if any(kw in cmd_clean for kw in ["email", "mail", "send message"]):
            candidate_skills.append("Communication")
            candidate_tools.append("email_tool")

        # Complexity estimation
        requires_tools = len(candidate_tools) > 0 or has_action
        if len(candidate_tools) >= 2 or (has_multi_intent and requires_tools):
            complexity = "HIGH"
        elif requires_tools or has_multi_intent or len(cmd_clean.split()) > 8:
            complexity = "MEDIUM"
        else:
            complexity = "LOW"

        routing_hints = {
            "multi_step_detected": has_multi_intent,
            "has_action_verbs": has_action,
            "is_conditional": " if " in cmd_clean,
            "developer_override": "multi_agent" in cmd_clean or "multi-agent" in cmd_clean
        }

        return ClassificationResult(
            question_type=q_type,
            is_conversational=is_conversational,
            requires_tools=requires_tools,
            estimated_complexity=complexity,
            candidate_skills=candidate_skills,
            candidate_tools=candidate_tools,
            routing_hints=routing_hints
        )


# Global instance
question_classifier = QuestionClassifier()
