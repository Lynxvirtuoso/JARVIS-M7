"""
services/conversation/transcript_resolver.py
Phase 1 Transcript Resolver for JARVIS M7.
Handles wake-word position flexibility (start/middle/end), wake-word variant normalization,
confidence scoring, sensitive action protection, and clarification question generation.
"""
import re
from typing import List, Optional, Tuple
from services.conversation.models import ResolvedTranscript, SensitiveActionType


WAKE_VARIANTS = [r"\bjarvis\b", r"\bjervis\b", r"\bjavis\b", r"\bhey jarvis\b"]

SENSITIVE_KEYWORDS = {
    "shut down", "shutdown", "exit", "close jarvis", "exit app", "close application",
    "turn off pc", "shut down pc", "restart", "reboot", "log out", "logout",
    "delete", "remove", "lock", "lock pc", "send", "send message",
    "send email", "place call", "make payment", "payment", "account",
    "clear database", "format", "remove account"
}

# Phonetic & misrecognition dictionary mapping pattern -> (resolved_text, is_sensitive, default_clarification)
PHONETIC_CORRECTIONS = [
    (
        r"^(shadoon|shadow|shaddow|shutting)\s*(jarvis)?$",
        "shut down",
        True,
        "Did you ask me to shut down?"
    ),
    (
        r"^who'?s?\s+there\s*,?\s*rahman\??$",
        "Who is A. R. Rahman?",
        False,
        "Did you mean, 'Who is A. R. Rahman?'"
    ),
    (
        r"^open\s+cold\b",
        "open code",
        False,
        "Did you mean open VS Code or Chrome?"
    ),
    (
        r"^surya\s+derm[uú]\s+pono\b",
        "system status",
        False,
        "Did you mean system status?"
    )
]


class TranscriptResolver:
    """
    Resolves raw STT output into a clean, confidence-scored ResolvedTranscript.
    Ensures wake-words at start/middle/end are properly stripped without discarding commands,
    and requires clarification for low-confidence or sensitive requests.
    """

    def resolve(
        self,
        raw_text: str,
        *,
        stt_confidence: Optional[float] = None,
        audio_quality: float = 1.0,
        session_active: bool = False,
    ) -> ResolvedTranscript:
        if not raw_text or not raw_text.strip():
            return ResolvedTranscript(
                raw_text="",
                resolved_text="",
                confidence=0.0,
                wake_word_detected=False,
                accepted_as_active_session_followup=False
            )

        text = raw_text.strip()
        text_lower = text.lower()

        # 1. Wake word position detection
        wake_detected, wake_pos, text_without_wake = self._detect_and_strip_wake_word(text_lower, text)

        cleaned_text = text_without_wake.strip()
        if not cleaned_text and wake_detected:
            # User just said "Jarvis" or "Jarvis?"
            return ResolvedTranscript(
                raw_text=text,
                resolved_text="jarvis",
                confidence=1.0,
                wake_word_detected=True,
                wake_word_position=wake_pos,
                accepted_as_active_session_followup=False,
                needs_clarification=False
            )

        # 2. Phonetic correction & low-confidence pattern matching
        matched_correction = None
        for pattern, resolved, is_sens, clarif_q in PHONETIC_CORRECTIONS:
            if re.search(pattern, cleaned_text.lower()) or re.search(pattern, text_lower):
                matched_correction = (resolved, is_sens, clarif_q)
                break

        # Calculate effective confidence bound between 0.0 and 1.0
        base_confidence = stt_confidence if stt_confidence is not None else 0.90
        effective_confidence = base_confidence * min(1.0, max(0.0, audio_quality))
        final_confidence = max(0.0, min(1.0, effective_confidence))

        accepted_as_followup = session_active and not wake_detected

        if matched_correction:
            resolved_text, is_sensitive, clarification_question = matched_correction
            # Phonetic misrecognitions like 'Shadoon Jarvis' are inherently uncertain (medium/low confidence)
            resolved_confidence = min(0.65, final_confidence)
            return ResolvedTranscript(
                raw_text=text,
                resolved_text=resolved_text,
                confidence=resolved_confidence,
                wake_word_detected=wake_detected,
                wake_word_position=wake_pos,
                accepted_as_active_session_followup=accepted_as_followup,
                needs_clarification=True,
                clarification_question=clarification_question,
                is_sensitive_action=is_sensitive,
                sensitive_action_type=SensitiveActionType.AMBIGUOUS_SHUTDOWN if is_sensitive else None
            )

        # Check general sensitive action keywords (checking both cleaned text and full raw text)
        is_sensitive = any(kw in cleaned_text.lower() or kw in text_lower for kw in SENSITIVE_KEYWORDS)
        sensitive_type = None
        if is_sensitive:
            if any(k in text_lower for k in ["close jarvis", "exit app", "close application", "exit jarvis"]):
                sensitive_type = SensitiveActionType.EXIT_APPLICATION
            elif any(k in text_lower for k in ["shut down pc", "shutdown computer", "turn off pc"]):
                sensitive_type = SensitiveActionType.SHUTDOWN_COMPUTER
            elif any(k in text_lower for k in ["restart pc", "reboot computer", "reboot"]):
                sensitive_type = SensitiveActionType.RESTART_COMPUTER
            elif any(k in text_lower for k in ["log out", "logout"]):
                sensitive_type = SensitiveActionType.LOG_OUT_WINDOWS
            elif any(k in text_lower for k in ["lock pc", "lock computer"]):
                sensitive_type = SensitiveActionType.LOCK_COMPUTER
            elif any(k in text_lower for k in ["delete"]):
                sensitive_type = SensitiveActionType.DELETE_FILE
            elif any(k in text_lower for k in ["send email"]):
                sensitive_type = SensitiveActionType.SEND_EMAIL
            elif any(k in text_lower for k in ["send message"]):
                sensitive_type = SensitiveActionType.SEND_MESSAGE
            elif any(k in text_lower for k in ["place call", "call"]):
                sensitive_type = SensitiveActionType.PLACE_CALL
            else:
                sensitive_type = SensitiveActionType.AMBIGUOUS_SHUTDOWN

        # Decision thresholding
        needs_clarification = False
        clarification_question = None

        if is_sensitive and final_confidence < 0.85:
            needs_clarification = True
            clarification_question = f"Did you ask me to {cleaned_text}?"
        elif final_confidence < 0.40:
            needs_clarification = True
            clarification_question = f"Sorry Sir, I am not sure I understood: '{cleaned_text}'. Could you repeat that?"

        return ResolvedTranscript(
            raw_text=text,
            resolved_text=cleaned_text if cleaned_text else text,
            confidence=final_confidence,
            wake_word_detected=wake_detected,
            wake_word_position=wake_pos,
            accepted_as_active_session_followup=accepted_as_followup,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            is_sensitive_action=is_sensitive,
            sensitive_action_type=sensitive_type
        )

    def _detect_and_strip_wake_word(self, text_lower: str, original_text: str) -> Tuple[bool, Optional[str], str]:
        """
        Detects wake word at start, middle, or end of string and strips it cleanly.
        """
        # Wake at start
        start_pattern = r"^(hey\s+)?(jarvis|jervis|javis)[,\s]*"
        if re.search(start_pattern, text_lower):
            stripped = re.sub(start_pattern, "", original_text, flags=re.IGNORECASE).strip()
            return True, "start", stripped

        # Wake at end
        end_pattern = r"[,\s]*(hey\s+)?(jarvis|jervis|javis)[\?\.]?$"
        if re.search(end_pattern, text_lower):
            stripped = re.sub(end_pattern, "", original_text, flags=re.IGNORECASE).strip()
            return True, "end", stripped

        # Wake in middle
        middle_pattern = r"\b(hey\s+)?(jarvis|jervis|javis)\b"
        if re.search(middle_pattern, text_lower):
            stripped = re.sub(middle_pattern, "", original_text, flags=re.IGNORECASE).strip()
            # Clean double spaces
            stripped = re.sub(r"\s+", " ", stripped).strip()
            return True, "middle", stripped

        return False, None, original_text


# Global resolver instance
transcript_resolver = TranscriptResolver()
