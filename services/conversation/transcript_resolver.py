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

        # 0. Collapse repeated STT duplication (e.g. "JARVIS what is the time now? JARVIS what is the time now?")
        text = self._collapse_repeated_phrases(text)
        text_lower = text.lower()

        # 1. Wake word position detection
        wake_detected, wake_pos, text_without_wake = self._detect_and_strip_wake_word(text_lower, text)

        cleaned_text = text_without_wake.strip()
        cleaned_text = self._collapse_repeated_phrases(cleaned_text)
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
            # --- Compound EXIT_APPLICATION phrases ---
            # Strip punctuation from raw text and also test against recombined text
            # so spoken STT transcripts like "Shut down, Jarvis." or "Jarvis, shut down."
            # reliably resolve to EXIT_APPLICATION regardless of wake word position.
            clean_raw_lower = re.sub(r"[.,!-;:'\"]+", "", text_lower).strip()
            _EXIT_COMPOUND_PHRASES = [
                "shutdown jarvis", "shut down jarvis",
                "jarvis shutdown", "jarvis shut down",
            ]
            recombined = f"{cleaned_text.lower()} jarvis" if wake_detected else clean_raw_lower
            recombined_alt = f"jarvis {cleaned_text.lower()}" if wake_detected else clean_raw_lower

            if any(p in clean_raw_lower or p in recombined or p in recombined_alt for p in _EXIT_COMPOUND_PHRASES):
                sensitive_type = SensitiveActionType.EXIT_APPLICATION
            elif any(k in clean_raw_lower for k in ["close jarvis", "exit app", "close application", "exit jarvis"]):
                sensitive_type = SensitiveActionType.EXIT_APPLICATION
            elif any(k in clean_raw_lower for k in ["shut down pc", "shutdown computer", "turn off pc"]):
                sensitive_type = SensitiveActionType.SHUTDOWN_COMPUTER
            elif any(k in clean_raw_lower for k in ["restart pc", "reboot computer", "reboot"]):
                sensitive_type = SensitiveActionType.RESTART_COMPUTER

            elif any(k in clean_raw_lower for k in ["log out", "logout"]):
                sensitive_type = SensitiveActionType.LOG_OUT_WINDOWS
            elif any(k in clean_raw_lower for k in ["lock pc", "lock computer"]):
                sensitive_type = SensitiveActionType.LOCK_COMPUTER
            elif any(k in clean_raw_lower for k in ["delete"]):
                sensitive_type = SensitiveActionType.DELETE_FILE
            elif any(k in clean_raw_lower for k in ["send email"]):
                sensitive_type = SensitiveActionType.SEND_EMAIL
            elif any(k in clean_raw_lower for k in ["send message"]):
                sensitive_type = SensitiveActionType.SEND_MESSAGE
            elif any(k in clean_raw_lower for k in ["place call", "call"]):
                sensitive_type = SensitiveActionType.PLACE_CALL
            else:
                sensitive_type = SensitiveActionType.AMBIGUOUS_SHUTDOWN



        # Decision thresholding
        needs_clarification = False
        clarification_question = None

        from services.conversation.question_classifier import question_classifier
        classification = question_classifier.classify(cleaned_text if cleaned_text else text)
        is_conversational_question = classification.is_conversational

        if is_sensitive and final_confidence < 0.85:
            needs_clarification = True
            clarification_question = f"Did you ask me to {cleaned_text}?"
        elif final_confidence < 0.40 and not is_conversational_question:
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
        Detects wake word or any phonetic variant at start, middle, or end of string and strips it cleanly.
        Uses FUZZY_VARIANTS, WAKE_PHRASES, and REJECT_WORDS from wake_word_constants.
        """
        from services.conversation.wake_word_constants import (
            WAKE_PHRASES, FUZZY_VARIANTS, REJECT_WORDS, WAKE_FUZZY_THRESHOLD,
            WAKE_WORD_FUZZY_THRESHOLD, SERVICE_ACTION_VERBS
        )
        from difflib import SequenceMatcher

        text_clean = re.sub(r"[.,!-;:'\"]+", "", text_lower).strip()
        all_words = text_clean.split()
        word_set = set(all_words)

        if word_set and word_set.issubset(REJECT_WORDS):
            return False, None, original_text

        # Combine canonical phrases and phonetic mishear variants into candidate list
        all_candidates = sorted(list(set(WAKE_PHRASES + FUZZY_VARIANTS)), key=len, reverse=True)

        # 1. Check start of string (word-boundary aware)
        for cand in all_candidates:
            cand_pattern = r"^(hey\s+|wake\s+up\s+)?\b" + re.escape(cand) + r"\b[,\s]*"
            if re.search(cand_pattern, text_clean):
                orig_remainder = re.sub(cand_pattern, "", original_text, flags=re.IGNORECASE).strip()
                if cand == "service" and orig_remainder:
                    rem_words = orig_remainder.lower().split()
                    first_word = re.sub(r"[.,!-;:'\"]+", "", rem_words[0]) if rem_words else ""
                    if first_word not in SERVICE_ACTION_VERBS:
                        continue
                return True, "start", orig_remainder

        # 2. Check end of string (word-boundary aware)
        for cand in all_candidates:
            cand_pattern = r"[,\s]*\b" + re.escape(cand) + r"\b[\?\.]?$"
            if re.search(cand_pattern, text_clean):
                orig_remainder = re.sub(cand_pattern, "", original_text, flags=re.IGNORECASE).strip()
                return True, "end", orig_remainder

        # 3. Check middle of string
        for cand in all_candidates:
            cand_pattern = r"\b" + re.escape(cand) + r"\b"
            if re.search(cand_pattern, text_clean):
                orig_remainder = re.sub(cand_pattern, "", original_text, flags=re.IGNORECASE).strip()
                orig_remainder = re.sub(r"\s+", " ", orig_remainder).strip()
                return True, "middle", orig_remainder

        # 4. Fuzzy token matching for leading words
        if all_words:
            for cand in all_candidates:
                cand_words = cand.split()
                n = len(cand_words)
                if len(all_words) >= n:
                    token_slice = " ".join(all_words[:n])
                    if SequenceMatcher(None, token_slice, cand).ratio() >= WAKE_WORD_FUZZY_THRESHOLD:
                        orig_words = original_text.strip().split()
                        orig_remainder = " ".join(orig_words[n:]).strip()
                        return True, "start", orig_remainder

        return False, None, original_text

    def _collapse_repeated_phrases(self, text: str) -> str:
        """
        Collapses STT-duplicated sentences, whole phrases, or trailing repeated segments.
        E.g.:
          'JARVIS what is the time now? JARVIS what is the time now?' -> 'JARVIS what is the time now?'
          'what is it? Did you say that? Did you say that?' -> 'what is it? Did you say that?'
        """
        if not text or not text.strip():
            return text

        cleaned = text.strip()

        # 1. Whole-sentence or clause duplication split by punctuation (?, ., !)
        # Matches e.g. "X? X?" or "X. X."
        parts = [p.strip() for p in re.split(r"(?<=[?.!])\s+", cleaned) if p.strip()]
        if len(parts) >= 2:
            from difflib import SequenceMatcher
            collapsed_parts = []
            for part in parts:
                if not collapsed_parts:
                    collapsed_parts.append(part)
                else:
                    prev = collapsed_parts[-1].lower().strip(" ?,.!")
                    curr = part.lower().strip(" ?,.!")
                    ratio = SequenceMatcher(None, prev, curr).ratio()
                    if ratio < 0.85:
                        collapsed_parts.append(part)
            cleaned = " ".join(collapsed_parts)

        # 2. Sequential phrase repetition split by clauses (commas or space-separated duplicate blocks)
        # Matches e.g. "Did you say that? Did you say that?" or "what is the time, what is the time"
        tokens = cleaned.split()
        if len(tokens) >= 4:
            # Check if second half of tokens is exact or near-exact match of first half
            mid = len(tokens) // 2
            for size in range(mid, 1, -1):
                first_block = " ".join(tokens[-2*size:-size]).lower().strip(" ?,.!")
                second_block = " ".join(tokens[-size:]).lower().strip(" ?,.!")
                if len(first_block) > 5:
                    from difflib import SequenceMatcher
                    if SequenceMatcher(None, first_block, second_block).ratio() >= 0.85:
                        cleaned = " ".join(tokens[:-size])
                        break

        return cleaned


# Global resolver instance
transcript_resolver = TranscriptResolver()
