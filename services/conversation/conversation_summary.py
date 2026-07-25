"""
services/conversation/conversation_summary.py
Fixed-size capped conversation summary utility sitting between SharedContext and prompt construction.
Does NOT modify SharedContext itself.
"""

from typing import List, Dict, Any


class ConversationSummary:
    """
    Fixed-size capped summary utility that extracts the last N turns of conversation history.
    """

    MAX_TURNS: int = 3  # Cap to last 3 exchanges to prevent prompt token bloat

    @classmethod
    def get_capped_summary(cls, history: List[Dict[str, str]] = None) -> str:
        if not history:
            return ""

        recent_turns = history[-cls.MAX_TURNS:]
        summary_lines = []
        for turn in recent_turns:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "").strip()
            summary_lines.append(f"{role}: {content[:150]}")  # Cap each turn to 150 chars max

        return " | ".join(summary_lines)
