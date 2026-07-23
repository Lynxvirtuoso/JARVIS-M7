"""
services/stt/prompt_builder.py
Dynamic STT Prompt Builder for JARVIS M7.
Constructs targeted, mode-gated STT prompts to prevent transcription bias without leaking personal vocabulary to logs.
"""
from typing import List, Optional, Set
from core.logger import logger

PASSIVE_WAKE_PROMPT = "Jarvis, Jervis, Javis, Hey Jarvis, Wake up Jarvis."

ACTIVE_ACTION_VERBS = [
    "open", "close", "start", "stop", "search", "explain",
    "tell me", "shut down", "lock", "status", "date", "time"
]


class STTPromptBuilder:
    """
    Builds context-sensitive STT prompts dynamically based on active conversation mode.
    Excludes massive contact lists during passive wake listening to prevent transcription bias.
    """

    def build_prompt(
        self,
        mode: str = "passive_wake",
        *,
        current_topic: Optional[str] = None,
        active_entities: Optional[List[str]] = None,
        relevant_apps: Optional[List[str]] = None
    ) -> str:
        if mode == "passive_wake":
            logger.info("STT Prompt Mode: passive_wake | Injected terms: 5 | Topic: None | Domains: wake")
            return PASSIVE_WAKE_PROMPT

        # Active command mode prompt construction
        terms: List[str] = ["Desktop assistant command."]
        term_count = 1

        if current_topic:
            terms.append(f"Current conversation topic: {current_topic}.")
            term_count += 1

        if active_entities:
            entity_str = ", ".join(active_entities[:3])
            terms.append(f"Relevant names: {entity_str}.")
            term_count += len(active_entities[:3])

        if relevant_apps:
            app_str = ", ".join(relevant_apps[:4])
            terms.append(f"Relevant apps: {app_str}.")
            term_count += len(relevant_apps[:4])

        verbs_str = ", ".join(ACTIVE_ACTION_VERBS[:8])
        terms.append(f"Possible actions: {verbs_str}.")
        term_count += 8

        terms.append("Preserve the word Jarvis wherever it appears.")

        logger.info(
            f"STT Prompt Mode: active_command | Injected terms: {term_count} | "
            f"Topic: {current_topic or 'None'} | Domains: command, apps"
        )
        return " ".join(terms)


# Global prompt builder instance
stt_prompt_builder = STTPromptBuilder()
