from dataclasses import dataclass
from core.config import config
from core.logger import logger

EXECUTE = "EXECUTE"
CONFIRM = "CONFIRM"
IGNORE = "IGNORE"

@dataclass
class ToolCall:
    tool_name: str
    action: str
    target: str
    source: str  # "voice" or "typed"
    confidence: float
    audio_quality: float
    reversible: bool
    destructive: bool

class TrustGate:
    """
    TrustGate sits between intent parsing and safe execution to evaluate trust levels.
    """
    @staticmethod
    def evaluate(tool_call: ToolCall) -> str:
        # Destructive actions ALWAYS return CONFIRM regardless of confidence
        if tool_call.destructive:
            logger.info(f"TrustGate: Action is destructive. Demoting to CONFIRM. Command: {tool_call.action} {tool_call.target}")
            return CONFIRM

        # Read thresholds from config properties
        typed_min_confidence = config.trust_gate_typed_min_confidence
        voice_min_confidence = config.trust_gate_voice_min_confidence
        voice_min_audio_quality = config.trust_gate_voice_min_audio_quality
        voice_confirm_confidence = config.trust_gate_voice_confirm_confidence

        if tool_call.source == "typed":
            if tool_call.confidence > typed_min_confidence:
                return EXECUTE
            else:
                if tool_call.confidence > voice_confirm_confidence:
                    return CONFIRM
                return IGNORE
        elif tool_call.source == "voice":
            if tool_call.confidence > voice_min_confidence and tool_call.audio_quality > voice_min_audio_quality:
                return EXECUTE
            elif tool_call.confidence > voice_confirm_confidence:
                return CONFIRM
            else:
                return IGNORE
        else:
            logger.warning(f"TrustGate: Unknown source '{tool_call.source}', default to CONFIRM")
            return CONFIRM
