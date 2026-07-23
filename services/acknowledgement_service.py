"""
services/acknowledgement_service.py
Context-aware speech acknowledgement classification and phrase generation service for JARVIS.
Selects natural, intent-matched phrases based on request text, route, web-search flag, and subject.
"""
import re
import random
from collections import deque
from typing import List, Optional, Set
from core.config import config
from core.logger import logger
from services.acknowledgement_intent import AcknowledgementIntent


# Intent-specific phrase templates
PHRASE_TEMPLATES = {
    AcknowledgementIntent.HUMOUR: [
        "Certainly, Sir. Activating my questionable sense of humour.",
        "Very well, Sir. Comedy protocols are online.",
        "Of course, Sir. I accept no responsibility for the punchline.",
        "Certainly, Sir. Let’s see whether my humour module survives this."
    ],
    AcknowledgementIntent.CODING: [
        "Understood, Sir. Let’s track down the bug.",
        "Certainly, Sir. I’ll inspect the logic.",
        "Let’s debug it, Sir.",
        "Understood. Let’s find where the code is breaking."
    ],
    AcknowledgementIntent.MUSIC: [
        "Certainly, Sir. Let’s tune into that.",
        "Of course, Sir. Let’s explore the music behind it.",
        "Certainly. Let’s take it note by note.",
        "Understood, Sir. Let’s work through the arrangement."
    ],
    AcknowledgementIntent.CREATIVE: [
        "Certainly, Sir. Let’s create something.",
        "With pleasure, Sir. Let’s shape the idea.",
        "Creative systems ready, Sir.",
        "Certainly. Let’s give that idea some form."
    ],
    AcknowledgementIntent.CURRENT_SEARCH: [
        "I’ll check the latest information, Sir.",
        "Certainly, Sir. Let me verify the current details.",
        "I’ll look up the live information now, Sir.",
        "Understood, Sir. I’ll check what’s current."
    ],
    AcknowledgementIntent.PERSONAL_OR_PRIVATE: [
        "Understood, Sir. I’ll keep this entirely local.",
        "Certainly. This will remain on your device.",
        "Local processing only, Sir."
    ],
    AcknowledgementIntent.MULTIMODAL: [
        "Certainly, Sir. Let me examine it.",
        "Understood. I’ll analyse the image.",
        "Of course, Sir. Let’s take a closer look."
    ],
    AcknowledgementIntent.GENERAL_EXPLANATION: [
        "Certainly, Sir. Let’s break that down.",
        "Of course, Sir. Here’s a clear explanation.",
        "Certainly, Sir. Let’s take a closer look.",
        "Understood, Sir. Let’s explore that."
    ]
}

# Instant request categories that must skip filler acknowledgements
INSTANT_COMMAND_KEYWORDS: Set[str] = {
    "time", "date", "battery", "volume", "status", "calculate", "math",
    "open chrome", "close chrome", "take screenshot", "lock pc", "sleep"
}


class AcknowledgementService:
    """
    Service for classifying user request intents and generating context-matched speech acknowledgements.
    Enforces strict rules: no search claims when use_web=False, phrase rotation, and subject-aware matching.
    """

    def __init__(self, history_size: int = 5):
        self.recent_history_size = history_size
        self._recent_phrases: deque[str] = deque(maxlen=self.recent_history_size)

    def should_skip(self, request_text: str, command_name: str | None = None) -> bool:
        """
        Determines whether the acknowledgement should be skipped for instant response types.
        """
        text_lower = (request_text or "").lower().strip()
        cmd_lower = (command_name or "").lower().strip()

        # Check instant keyword triggers
        if any(kw in text_lower or kw in cmd_lower for kw in INSTANT_COMMAND_KEYWORDS):
            return True

        # Check exact time / date / status requests
        if text_lower in {
            "what time is it", "whats the time", "what is the time", "tell me the time", "time",
            "what date is it", "whats the date", "what day is it", "date",
            "system status", "battery status", "volume"
        }:
            return True

        return False

    def classify(
        self,
        request_text: str,
        *,
        brain_route: str | None = None,
        use_web: bool = False,
        command_name: str | None = None
    ) -> AcknowledgementIntent:
        """
        Classifies request text into an AcknowledgementIntent enum. < 10ms.
        """
        text_lower = (request_text or "").lower().strip()

        # 1. Direct deterministic action
        if command_name or self.should_skip(request_text, command_name):
            return AcknowledgementIntent.DIRECT_ACTION

        # 2. Multimodal intent
        if brain_route == "multimodal" or any(kw in text_lower for kw in ["image", "picture", "screenshot", "photo", "look at this"]):
            return AcknowledgementIntent.MULTIMODAL

        # 3. Privacy / local intent
        if brain_route == "private_local" or any(kw in text_lower for kw in ["local", "private", "offline", "dont send online"]):
            return AcknowledgementIntent.PERSONAL_OR_PRIVATE

        # 4. Humour intent
        if any(kw in text_lower for kw in ["joke", "funny", "laugh", "humour", "humor", "comedy"]):
            return AcknowledgementIntent.HUMOUR

        # 5. Coding & debugging intent
        if any(kw in text_lower for kw in ["python", "code", "bug", "error", "exception", "traceback", "debug", "flutter", "dart", "script"]):
            return AcknowledgementIntent.CODING

        # 6. Music & theory intent
        if any(kw in text_lower for kw in ["piano", "music", "song", "raga", "tala", "chord", "lyrics", "melody"]):
            return AcknowledgementIntent.MUSIC

        # 7. Creative intent
        if any(kw in text_lower for kw in ["write a story", "create lyrics", "write caption", "brainstorm", "compose"]):
            return AcknowledgementIntent.CREATIVE

        # 8. Web Search / Current Information (ONLY if use_web is Authoritatively True)
        if use_web or brain_route == "current_information":
            if use_web:
                return AcknowledgementIntent.CURRENT_SEARCH

        # 9. General explanation fallback
        return AcknowledgementIntent.GENERAL_EXPLANATION

    def generate(
        self,
        request_text: str,
        *,
        brain_route: str | None = None,
        use_web: bool = False,
        command_name: str | None = None,
        seed: int | None = None
    ) -> str | None:
        """
        Generates a context-matched acknowledgement string within < 5ms.
        Returns None if acknowledgement should be skipped.
        STRICT RULE: If use_web is False, search-related phrases are NEVER returned.
        """
        if not config.get("context_aware_acknowledgements", True):
            return None

        # Check skip rule
        if self.should_skip(request_text, command_name):
            return None

        # Humour level check
        humour_level = config.get("acknowledgement_humour_level", "light")
        if humour_level == "off":
            intent = AcknowledgementIntent.GENERAL_EXPLANATION
        else:
            intent = self.classify(request_text, brain_route=brain_route, use_web=use_web, command_name=command_name)

        # STRICT RULE: use_web=False MUST NOT return CURRENT_SEARCH intent
        if not use_web and intent == AcknowledgementIntent.CURRENT_SEARCH:
            intent = AcknowledgementIntent.GENERAL_EXPLANATION

        text_lower = request_text.lower().strip()

        # Check subject-specific custom phrases first if enabled
        if config.get("acknowledgement_use_subject_phrases", True):
            if "football" in text_lower or "soccer" in text_lower:
                phrase = "Certainly, Sir. Let’s take a look at the beautiful game."
                self._record_phrase(phrase)
                return phrase
            elif "piano" in text_lower:
                phrase = "Of course, Sir. Let’s open the lid on that."
                self._record_phrase(phrase)
                return phrase

        # Get candidates from intent template pool
        candidates = PHRASE_TEMPLATES.get(intent, PHRASE_TEMPLATES[AcknowledgementIntent.GENERAL_EXPLANATION])

        # Filter out recently used phrases if possible
        available = [p for p in candidates if p not in self._recent_phrases]
        if not available:
            available = candidates

        if seed is not None:
            random.seed(seed)
        selected = random.choice(available)
        self._record_phrase(selected)
        return selected

    def _record_phrase(self, phrase: str) -> None:
        self._recent_phrases.append(phrase)


# Global service instance
acknowledgement_service = AcknowledgementService()