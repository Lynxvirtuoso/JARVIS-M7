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
from services.conversation.models import InterruptDecision

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

    def evaluate_interrupt(
        self,
        transcript: str,
        current_spoken_sentence: Optional[str],
        recent_spoken_sentences: List[str],
        request_id: Optional[str] = None,
        similarity_threshold: float = 0.55
    ) -> InterruptDecision:
        req_id = request_id or "unknown"

        if not transcript or not transcript.strip():
            logger.info(f"Interrupt decision | Accepted: False | Reason: empty_transcript | Req ID: {req_id[:8]}")
            return InterruptDecision(
                accepted=False,
                reason="empty_transcript",
                normalized_text="",
                similarity=0.0,
                word_overlap=0.0,
                request_id=req_id
            )

        text_clean = re.sub(r"[^\w\s]", "", transcript.strip().lower()).strip()
        if not text_clean:
            logger.info(f"Interrupt decision | Accepted: False | Reason: empty_punctuation | Req ID: {req_id[:8]}")
            return InterruptDecision(
                accepted=False,
                reason="empty_punctuation",
                normalized_text="",
                similarity=0.0,
                word_overlap=0.0,
                request_id=req_id
            )

        # Explicit keyword check (Stop, Wait, Cancel, Pause, Hold on, No, Actually)
        if self.is_explicit_interrupt(text_clean):
            reason = "explicit_stop" if "stop" in text_clean else ("correction" if "actually" in text_clean else "explicit_keyword")
            logger.info(f"Interrupt decision | Accepted: True | Reason: {reason} | Text: '{text_clean}' | Req ID: {req_id[:8]}")
            return InterruptDecision(
                accepted=True,
                reason=reason,
                normalized_text=text_clean,
                similarity=0.0,
                word_overlap=0.0,
                request_id=req_id
            )

        if len(text_clean) < 3:
            logger.info(f"Interrupt decision | Accepted: False | Reason: too_short | Text: '{text_clean}' | Req ID: {req_id[:8]}")
            return InterruptDecision(
                accepted=False,
                reason="too_short",
                normalized_text=text_clean,
                similarity=0.0,
                word_overlap=0.0,
                request_id=req_id
            )

        # Calculate similarity & overlap against spoken sentences
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

        if max_similarity >= similarity_threshold or max_overlap >= 0.50:
            logger.info(
                f"Interrupt decision | Accepted: False | Reason: assistant_echo | Similarity: {max_similarity:.2f} | "
                f"Overlap: {max_overlap:.2f} | Matched: '{matched_text[:25]}...' | Req ID: {req_id[:8]}"
            )
            return InterruptDecision(
                accepted=False,
                reason="assistant_echo",
                normalized_text=text_clean,
                similarity=max_similarity,
                word_overlap=max_overlap,
                request_id=req_id
            )

        words = text_clean.split()
        if len(words) <= 2:
            logger.info(f"Interrupt decision | Accepted: False | Reason: short_non_explicit | Text: '{text_clean}' | Req ID: {req_id[:8]}")
            return InterruptDecision(
                accepted=False,
                reason="short_non_explicit",
                normalized_text=text_clean,
                similarity=max_similarity,
                word_overlap=max_overlap,
                request_id=req_id
            )

        logger.info(f"Interrupt decision | Accepted: True | Reason: distinct_user_interruption | Text: '{text_clean}' | Req ID: {req_id[:8]}")
        return InterruptDecision(
            accepted=True,
            reason="distinct_user_interruption",
            normalized_text=text_clean,
            similarity=max_similarity,
            word_overlap=max_overlap,
            request_id=req_id
        )

    def is_echo(
        self,
        transcript: str,
        current_spoken_sentence: Optional[str],
        recent_spoken_sentences: List[str],
        request_id: Optional[str] = None,
        similarity_threshold: float = 0.55
    ) -> bool:
        """
        Evaluates whether an STT transcript received during TTS playback is assistant echo.
        Returns:
            True  -> Assistant Echo / Noise / Irrelevant (REJECT interruption, do not halt playback)
            False -> Genuine User Interruption (ACCEPT interruption, halt playback immediately)
        """
        decision = self.evaluate_interrupt(
            transcript,
            current_spoken_sentence,
            recent_spoken_sentences,
            request_id=request_id,
            similarity_threshold=similarity_threshold
        )
        return not decision.accepted


# Global echo rejector instance
echo_rejector = EchoRejector()
