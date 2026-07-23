"""
services/stt/prompt_builder.py
Dynamic STT Prompt Builder for JARVIS M7.
Constructs targeted, mode-gated STT prompts to prevent transcription bias without leaking personal vocabulary to logs.
"""
from typing import List, Optional
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
    Logs safe metadata without leaking personal vocabulary to production logs.
    """

    def build_prompt(
        self,
        mode: str = "passive_wake",
        *,
        current_topic: Optional[str] = None,
        active_entities: Optional[List[str]] = None,
        relevant_apps: Optional[List[str]] = None,
        pending_confirmation: bool = False,
        active_domain: Optional[str] = None,
        max_length: int = 400
    ) -> str:
        if mode == "passive_wake":
            logger.info("STT prompt built | mode=passive_wake | term_count=5 | character_count=51 | domains=wake")
            return PASSIVE_WAKE_PROMPT

        # Active command mode prompt construction
        terms: List[str] = ["Desktop assistant command."]
        term_count = 1

        if pending_confirmation:
            terms.append("A confirmation response is expected (yes, no, cancel).")
            term_count += 3

        if current_topic:
            # Topic indicator
            terms.append(f"Current conversation topic: {current_topic}.")
            term_count += 1

        if active_entities:
            # Include at most 3 active entity hints
            entity_str = ", ".join(active_entities[:3])
            terms.append(f"Relevant names: {entity_str}.")
            term_count += len(active_entities[:3])

        if relevant_apps:
            # Include at most 3 app hints
            app_str = ", ".join(relevant_apps[:3])
            terms.append(f"Relevant apps: {app_str}.")
            term_count += len(relevant_apps[:3])

        if active_domain:
            terms.append(f"Domain: {active_domain}.")
            term_count += 1

        verbs_str = ", ".join(ACTIVE_ACTION_VERBS[:6])
        terms.append(f"Possible actions: {verbs_str}.")
        term_count += 6

        terms.append("Preserve the word Jarvis wherever it appears.")

        full_prompt = " ".join(terms)
        if len(full_prompt) > max_length:
            full_prompt = full_prompt[:max_length].rstrip() + "."

        logger.info(
            f"STT prompt built | mode=active_command | term_count={term_count} | "
            f"character_count={len(full_prompt)} | topic_included={bool(current_topic)} | "
            f"pending_confirmation={pending_confirmation}"
        )
        return full_prompt


# Global prompt builder instance
stt_prompt_builder = STTPromptBuilder()
