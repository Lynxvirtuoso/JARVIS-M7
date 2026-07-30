from dataclasses import dataclass
from enum import Enum


class FailureType(Enum):
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_QUOTA_EXHAUSTED = "provider_quota_exhausted"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    MEMORY_SERVICE_FAILURE = "memory_service_failure"
    DATABASE_LOCKED = "database_locked"
    AUDIO_SERVICE_FAILURE = "audio_service_failure"
    SPEECH_SERVICE_FAILURE = "speech_service_failure"
    STT_FAILURE = "stt_failure"
    TELEGRAM_DISCONNECT = "telegram_disconnect"
    NETWORK_UNAVAILABLE = "network_unavailable"
    PLANNER_FAILURE = "planner_failure"
    RESEARCH_FAILURE = "research_failure"
    CRITIC_FAILURE = "critic_failure"
    SYNTHESIZER_FAILURE = "synthesizer_failure"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


@dataclass
class ReliabilityClassification:
    """
    Pure classification of a failure. This object describes WHAT a failure
    is — it must never contain logic that decides what to DO about it.
    Recovery decisions belong to the calling owner (ProviderManager,
    AgentCoordinator, MemoryService, etc.), never to this object.
    """
    failure_type: FailureType
    retryable: bool
    recoverable: bool
    fatal: bool
    reason: str
