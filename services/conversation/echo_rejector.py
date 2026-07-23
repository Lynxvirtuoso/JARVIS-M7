"""
services/conversation/echo_rejector.py
Self-voice echo rejection module for JARVIS M7.
Compares microphone interruption transcripts against active/recent TTS output to discard echo self-talk
while honoring explicit user interruption commands (Stop, Cancel, Wait, etc.) using safe word-boundary patterns.
"""
import re
from difflib import SequenceMatcher
from typing import List, Optional
from core.logger import logger

EXPLICIT_INTERRUPT_PATTERNS = [
    r"^\s*stop(?:\s+speaking)?\s*[.!?]*$",
    r"^\s*wait\s*[.!?]*$",
    r"^\s*hold\s+on\s*[.!?]*$",
    r"^\s*cancel(?:\s+that)?\s*[.!?]*$",
    r"^\s*pause\s*[.!?]*$",
    r"^\s*be\s+quiet\s*[.!?]*$",
    r"^\s*shut\s+up\s*[.!?]*$",
    r"^\s*never\s+mind\s*[.!?]*$",
    r"^\s*actually\b",
    r"^\s*no\s*[.!?]*$",
    r"^\s*nope\s*[.!?]*$",
]


class EchoRejector:
    """
    Evaluates whether an STT transcript received during TTS playback is user interruption or assistant echo.
    """

    def is_explicit_interrupt(self, text_lower: str) -> bool:
        """
        Checks if transcript is an explicit interruption command using strict word-boundary regex patterns.
        Prevents false matches such as 'no' inside 'know', 'another', or 'nobody'.
        """
        for pattern in EXPLICIT_INTERRUPT_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False

    def is_echo(
        self,
        transcript: str,
        current_spoken_sentence: Optional[str],
        recent_spoken_sentences: List[str],
        request_id: Optional[str] = None,
        similarity_threshold: float = 0.55
    ) -> bool:
        """
        Evaluates whether an STT transcript received during TTS playback is assistant echo or genuine user interruption.
        Returns:
            True  -> Assistant Echo / Noise / Irrelevant (REJECT interruption, do not halt playback)
            False -> Genuine User Interruption (ACCEPT interruption, halt playback immediately)
        """
        if not transcript or not transcript.strip():
            logger.info(f"Interrupt rejected | Reason: empty_transcript | Req ID: {request_id[:8] if request_id else 'None'}")
            return True

        text_clean = re.sub(r"[^\w\s]", "", transcript.strip().lower()).strip()
        if not text_clean:
            logger.info(f"Interrupt rejected | Reason: empty_punctuation | Req ID: {request_id[:8] if request_id else 'None'}")
            return True

        # Check explicit interruption keywords first (Stop, Pause, Cancel, Wait, Hold on, No, Actually, etc.)
        if self.is_explicit_interrupt(text_clean):
            logger.info(
                f"Interrupt accepted | Reason: explicit_keyword | Text: '{text_clean}' | Req ID: {request_id[:8] if request_id else 'None'}"
            )
            return False

        if len(text_clean) < 3:
            logger.info(f"Interrupt rejected | Reason: too_short | Text: '{text_clean}' | Req ID: {request_id[:8] if request_id else 'None'}")
            return True

        # Compare against active spoken sentence and recent sentences
        max_similarity = 0.0
        max_overlap = 0.0
        matched_text = ""

        targets = []
        if current_spoken_sentence:
            targets.append(current_spoken_sentence)
        if recent_spoken_sentences:
            targets.extend(recent_spoken_sentences[-3:])

        trans_words = set(re.findall(r"\w+", text_clean))

        for target in targets:
            if not target:
                continue
            target_lower = target.lower().strip()
            score = SequenceMatcher(None, text_clean, target_lower).ratio()
            if score > max_similarity:
                max_similarity = score
                matched_text = target_lower

            target_words = set(re.findall(r"\w+", target_lower))
            if trans_words and target_words:
                overlap = len(trans_words.intersection(target_words)) / float(len(trans_words))
                if overlap > max_overlap:
                    max_overlap = overlap
                    if score > max_similarity:
                        matched_text = target_lower

        if max_similarity >= similarity_threshold or max_overlap >= 0.50:
            logger.info(
                f"Interrupt rejected as echo | Similarity: {max_similarity:.2f} | Overlap: {max_overlap:.2f} | "
                f"Matched: '{matched_text[:25]}...' | Req ID: {request_id[:8] if request_id else 'None'}"
            )
            return True

        # Reject short non-explicit transcripts (2 words or less that don't match explicit keywords)
        words = text_clean.split()
        if len(words) <= 2:
            logger.info(
                f"Interrupt rejected | Reason: short_non_explicit | Text: '{text_clean}' | Req ID: {request_id[:8] if request_id else 'None'}"
            )
            return True

        logger.info(
            f"Interrupt accepted | Reason: distinct_user_speech | Text: '{text_clean}' | Req ID: {request_id[:8] if request_id else 'None'}"
        )
        return False


# Global echo rejector instance
echo_rejector = EchoRejector()
