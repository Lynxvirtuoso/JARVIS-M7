"""
services/conversation/models.py
Data models and data structures for Phase 1 Listening Reliability & Conversational Intelligence.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class SensitiveActionType(Enum):
    EXIT_APPLICATION = "exit_application"
    SHUTDOWN_COMPUTER = "shutdown_computer"
    RESTART_COMPUTER = "restart_computer"
    LOG_OUT_WINDOWS = "log_out_windows"
    LOCK_COMPUTER = "lock_computer"
    DELETE_FILE = "delete_file"
    SEND_MESSAGE = "send_message"
    SEND_EMAIL = "send_email"
    PLACE_CALL = "place_call"
    AMBIGUOUS_SHUTDOWN = "ambiguous_shutdown"


@dataclass(frozen=True)
class ConversationRequest:
    request_id: str
    session_id: str
    raw_transcript: str
    cleaned_transcript: str
    created_at: float
    source: str = "voice"
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
    accepted_as_active_session_followup: bool = False
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    is_sensitive_action: bool = False
    sensitive_action_type: Optional[SensitiveActionType] = None


@dataclass
class PendingConfirmation:
    request_id: str
    session_id: str
    action_type: SensitiveActionType
    action_payload: Dict[str, Any]
    source: str
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class InterruptDecision:
    accepted: bool
    reason: str
    normalized_text: str
    similarity: float
    word_overlap: float
    request_id: str
