"""
services/acknowledgement_intent.py
Defines the AcknowledgementIntent Enum for context-aware JARVIS speech acknowledgements.
"""
from enum import Enum


class AcknowledgementIntent(Enum):
    DIRECT_ACTION = "direct_action"
    GENERAL_EXPLANATION = "general_explanation"
    HUMOUR = "humour"
    CREATIVE = "creative"
    MUSIC = "music"
    CODING = "coding"
    TROUBLESHOOTING = "troubleshooting"
    CURRENT_SEARCH = "current_search"
    CALCULATION = "calculation"
    PERSONAL_OR_PRIVATE = "personal_or_private"
    MULTIMODAL = "multimodal"
    UNKNOWN = "unknown"