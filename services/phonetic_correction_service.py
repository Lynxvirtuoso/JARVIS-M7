import os
import re
import json
from core.logger import logger

# Context triggers that indicate scheduling, calling, or performer events
CONTEXT_TRIGGERS = {
    "call", "calling", "called", "phone", "dial", "ring", "schedule", "scheduling", "book", "booking",
    "lesson", "lessons", "gig", "gigs", "recital", "meet", "meeting", "meetings", "discussion", "rehearsal", "set", "setup"
}

# Standalone short/common words that require a context trigger to be replaced
COMMON_SHORT_WORDS = {
    "ma", "om", "tar", "sam", "meat", "meet", "emma", "anna", "mama", "dad", "papa", "appa", "amma"
}

class PhoneticCorrectionService:
    def __init__(self, json_path: str = r"d:\JARVIS M7\data\phonetic_variants.json"):
        self.json_path = json_path
        self.mappings = []  # List of tuples: (variant, canonical, requires_context)
        self.load_mappings()

    def load_mappings(self):
        self.mappings = []
        if not os.path.exists(self.json_path):
            logger.warning(f"Phonetic variants file not found at {self.json_path}")
            return

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Validation for collisions/duplicates
            variant_to_canonical = {}
            collisions = []

            for category in ["contacts", "calendar_terms", "lifecycle_terms"]:
                if category not in data:
                    continue
                for canonical, variants in data[category].items():
                    for variant in variants:
                        variant_clean = variant.strip().lower()
                        if variant_clean in variant_to_canonical:
                            existing_canonical = variant_to_canonical[variant_clean]
                            if existing_canonical != canonical:
                                collisions.append((variant, existing_canonical, canonical))
                        else:
                            variant_to_canonical[variant_clean] = canonical

            if collisions:
                for var, cat1, cat2 in collisions:
                    logger.warning(
                        f"[PHONETIC COLLISION WARNING] Variant '{var}' is mapped to multiple canonical terms: "
                        f"'{cat1}' and '{cat2}'."
                    )

            # Build compilation list sorted by length descending
            temp_mappings = []
            for category in ["contacts", "calendar_terms", "lifecycle_terms"]:
                if category not in data:
                    continue
                for canonical, variants in data[category].items():
                    for variant in variants:
                        v_str = variant.strip()
                        if not v_str:
                            continue
                        # Determine if this variant requires context gating
                        v_lower = v_str.lower()
                        if canonical.lower() in CONTEXT_TRIGGERS or category == "lifecycle_terms":
                            req_context = False
                        else:
                            req_context = (len(v_lower) <= 4) or (v_lower in COMMON_SHORT_WORDS)
                        temp_mappings.append((v_str, canonical, req_context))

            # Sort by variant length descending to avoid partial/sub-string match overriding
            temp_mappings.sort(key=lambda x: len(x[0]), reverse=True)
            self.mappings = temp_mappings
            logger.info(f"Loaded {len(self.mappings)} phonetic variant mappings successfully.")

        except Exception as e:
            logger.error(f"Error loading phonetic variants: {e}", exc_info=True)

    def correct_transcription(self, text: str) -> str:
        if not text or not self.mappings:
            return text

        corrected_text = text
        # Extract lowercase words to check for general context trigger
        words_in_text = set(re.findall(r"\w+", corrected_text.lower()))
        has_context = any(t in words_in_text for t in CONTEXT_TRIGGERS)

        for variant, canonical, req_context in self.mappings:
            if req_context and not has_context:
                continue

            # Case-insensitive word boundary replacement
            pattern = r"\b" + re.escape(variant) + r"\b"
            
            # Simple wrapper to maintain casing if we just replace it
            def replace_match(match):
                # If variant is capitalized or uppercase, try to match styling, else use canonical
                matched_str = match.group(0)
                if matched_str.isupper():
                    return canonical.upper()
                if matched_str[0].isupper():
                    return canonical
                return canonical.lower()

            corrected_text = re.sub(pattern, replace_match, corrected_text, flags=re.IGNORECASE)

        return corrected_text

phonetic_correction_service = PhoneticCorrectionService()
