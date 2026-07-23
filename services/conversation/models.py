"""
services/conversation/models.py
Data models and data structures for Phase 1 Listening Reliability & Conversational Intelligence.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ConversationRequest:
    request_id: str
    session_id: str
    raw_transcript: str
    cleaned_transcript: str
    created_at: float
    audio_quality: float = 1.0
    original_audio_peak: float = 0.0
    processed_audio_peak: float = 0.0
    clipping_detected: bool = False
    stt_confidence: Optional[float] = None
    stt_provider: str = "groq_stt"


@dataclass
class ResolvedTranscript:
    raw_text: str
    resolved_text: str
    confidence: float
    alternatives: List[str] = field(default_factory=list)
    wake_word_detected: bool = False
    wake_word_position: Optional[str] = None  # "start", "middle", "end"
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    is_sensitive_action: bool = False
