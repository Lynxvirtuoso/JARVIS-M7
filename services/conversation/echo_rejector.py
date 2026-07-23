"""
services/conversation/echo_rejector.py
Self-voice echo rejection module for JARVIS M7.
Compares microphone interruption transcripts against active/recent TTS output to discard echo self-talk
while honoring explicit user interruption commands (Stop, Cancel, Wait, etc.).
"""
import re
from difflib import SequenceMatcher
from typing import List, Optional
from core.logger import logger

EXPLICIT_INTERRUPT_KEYWORDS = {
    "stop", "wait", "hold on", "cancel", "no", "actually", "pause", "be quiet", "shut up", "never mind"
}


class EchoRejector:
    """
    Evaluates whether an STT transcript received during TTS playback is user interruption or assistant echo.
    """

    def is_echo(
        self,
        transcript: str,
        current_spoken_sentence: Optional[str],
        recent_spoken_sentences: List[str],
        request_id: Optional[str] = None,
        similarity_threshold: float = 0.65
    ) -> bool:
        if not transcript or not transcript.strip():
            return False

        text_lower = transcript.strip().lower()

        # Always permit explicit interruption keywords regardless of similarity
        if any(kw in text_lower for kw in EXPLICIT_INTERRUPT_KEYWORDS):
            logger.info(
                f"Interrupt accepted | Reason: explicit_keyword | Req ID: {request_id[:8] if request_id else 'None'}"
            )
            return False

        # Compare against current spoken sentence and recent sentences
        max_similarity = 0.0
        matched_text = ""

        targets = []
        if current_spoken_sentence:
            targets.append(current_spoken_sentence)
        targets.extend(recent_spoken_sentences[-3:])

        trans_words = set(re.findall(r"\w+", text_lower))

        for target in targets:
            if not target:
                continue
            target_lower = target.lower().strip()
            score = SequenceMatcher(None, text_lower, target_lower).ratio()
            if score > max_similarity:
                max_similarity = score
                matched_text = target_lower

            # Word-set overlap check (e.g., transcript "certainly so sir", target "certainly sir let's take a look")
            target_words = set(re.findall(r"\w+", target_lower))
            if trans_words and target_words:
                overlap = len(trans_words.intersection(target_words)) / float(len(trans_words))
                if len(trans_words) >= 2 and overlap > max_similarity:
                    max_similarity = overlap
                    matched_text = target_lower

        if max_similarity >= similarity_threshold:
            logger.info(
                f"Interrupt rejected as echo | Similarity: {max_similarity:.2f} | "
                f"Matched: '{matched_text[:20]}...' | Req ID: {request_id[:8] if request_id else 'None'}"
            )
            return True

        logger.info(
            f"Interrupt accepted | Similarity: {max_similarity:.2f} | Req ID: {request_id[:8] if request_id else 'None'}"
        )
        return False


# Global echo rejector instance
echo_rejector = EchoRejector()
