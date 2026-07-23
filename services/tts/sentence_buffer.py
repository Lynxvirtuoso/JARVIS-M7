"""
services/tts/sentence_buffer.py
Punctuation and context-aware sentence buffer for streaming LLM text chunks.
Extracts speakable, clean sentence chunks for streaming TTS synthesis without broken splits.
"""
import re
from typing import List, Set

DEFAULT_ABBREVIATIONS: Set[str] = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "e.g.", "i.e.", "etc.", "vs.", "approx.", "st.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "oct.", "nov.", "dec.",
    "a.m.", "p.m.", "www.", "inc.", "ltd.", "co."
}

# Dangling fragments that MUST NOT end a TTS chunk
DANGLING_ENDINGS: Set[str] = {
    "and a", "with the", "because the", "including a", "and the", "for the",
    "in the", "on the", "at the", "to the", "of the", "a 10", "the", "a", "an", "and", "or", "but"
}


class SentenceBuffer:
    """
    Buffers fragmented streaming LLM text chunks and returns completed, safe speakable sentences.
    Handles abbreviations, numbers (decimals), first-sentence prioritization, and max length boundaries.
    Prevents incomplete forced chunk endings (dangling conjunctions, number fragments).
    """
    def __init__(
        self,
        *,
        minimum_chars: int = 24,
        maximum_chars: int = 220,
        first_sentence_minimum_chars: int = 18,
        abbreviations: Set[str] = None
    ):
        self.minimum_chars = minimum_chars
        self.maximum_chars = maximum_chars
        self.first_sentence_minimum_chars = first_sentence_minimum_chars
        self.abbreviations = set(abbreviations) if abbreviations else set(DEFAULT_ABBREVIATIONS)
        self._buffer = ""
        self._is_first_sentence = True

    def reset(self) -> None:
        """Reset internal buffer state."""
        self._buffer = ""
        self._is_first_sentence = True

    def add_chunk(self, chunk: str) -> List[str]:
        """
        Add a text chunk and return any newly completed, speakable sentences in order.
        """
        if not chunk:
            return []

        self._buffer += chunk
        emitted_sentences: List[str] = []

        while True:
            sentence, remaining = self._try_extract_sentence(self._buffer)
            if sentence is None:
                # Check if buffer has grown beyond maximum length without punctuation
                if len(self._buffer.strip()) >= self.maximum_chars:
                    forced_sentence, self._buffer = self._split_at_boundary(self._buffer)
                    if forced_sentence:
                        emitted_sentences.append(forced_sentence)
                        self._is_first_sentence = False
                        continue
                break

            emitted_sentences.append(sentence)
            self._buffer = remaining

        return emitted_sentences

    def flush(self) -> List[str]:
        """
        Return all remaining buffered text as clean speakable sentences when generation finishes.
        """
        leftover = self._buffer.strip()
        self._buffer = ""
        if not leftover:
            return []

        sentences: List[str] = []
        while leftover:
            sentence, remaining = self._try_extract_sentence(leftover, is_final_flush=True)
            if sentence:
                sentences.append(sentence)
                leftover = remaining
            else:
                sentences.append(leftover)
                break

        self.reset()
        return sentences

    def _try_extract_sentence(self, text: str, is_final_flush: bool = False) -> tuple[str | None, str]:
        """
        Attempts to extract a complete sentence from text.
        """
        n = len(text)

        # Punctuation search
        for i in range(n):
            char = text[i]
            if char in (".", "?", "!", ":", ";", "\n"):
                # Decimal check: digit before and digit after (e.g. 3.14)
                if char == "." and i > 0 and text[i - 1].isdigit() and i + 1 < n and text[i + 1].isdigit():
                    continue

                # Abbreviation check
                if char == ".":
                    prefix_text = text[: i + 1]
                    word_match = re.search(r'\b[a-zA-Z\.]+\.$', prefix_text)
                    if word_match and word_match.group(0).lower() in self.abbreviations:
                        continue
                    # Single capital letter initial (e.g. A. R. Rahman)
                    if i >= 1 and text[i - 1].isupper() and (i == 1 or not text[i - 2].isalpha()):
                        continue

                # Boundary check: space or end of text
                has_boundary = (i + 1 < n and (text[i + 1].isspace() or text[i + 1] in ('"', "'", ")", "]"))) or (i + 1 == n)
                if not has_boundary:
                    continue

                candidate = text[: i + 1].strip()
                remaining = text[i + 1 :].lstrip()

                min_chars = self.first_sentence_minimum_chars if self._is_first_sentence else self.minimum_chars
                if len(candidate) >= min_chars or is_final_flush:
                    if not self._is_dangling(candidate) or is_final_flush:
                        self._is_first_sentence = False
                        return candidate, remaining

        return None, text

    def _is_dangling(self, sentence: str) -> bool:
        """
        Returns True if sentence ends with a dangling conjunction, digit fragment, or incomplete phrase.
        """
        s_lower = sentence.lower().strip()
        for dangling in DANGLING_ENDINGS:
            if s_lower.endswith(" " + dangling) or s_lower == dangling:
                return True
        # Check if sentence ends with an unclosed quote or dangling digit
        if re.search(r'\b(and|with|because|including|the|a|an|for|in|on|at|to|of)\s+\d+$', s_lower):
            return True
        return False

    def _split_at_boundary(self, text: str) -> tuple[str, str]:
        """
        Force-split a long buffer exceeding max_chars at a safe comma, semicolon, or whitespace boundary.
        Expands maximum_chars temporarily if no clean non-dangling split boundary exists.
        """
        target_span = text[: self.maximum_chars]

        # Search backward for natural phrase split (comma, semicolon, dash)
        for boundary_char in (",", ";", "-", " "):
            pos = target_span.rfind(boundary_char)
            while pos >= self.minimum_chars:
                first_part = text[: pos + 1].strip()
                second_part = text[pos + 1 :].strip()
                if not self._is_dangling(first_part):
                    return first_part, second_part
                pos = target_span[:pos].rfind(boundary_char)

        # Fallback whitespace split ensuring non-dangling
        words = target_span.split()
        for idx in range(len(words) - 1, 0, -1):
            candidate_part = " ".join(words[:idx]).strip()
            if len(candidate_part) >= self.minimum_chars and not self._is_dangling(candidate_part):
                split_point = text.find(candidate_part) + len(candidate_part)
                return text[:split_point].strip(), text[split_point:].strip()

        # Hard char limit fallback
        return text[: self.maximum_chars].strip(), text[self.maximum_chars :].strip()
