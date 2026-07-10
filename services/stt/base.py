from dataclasses import dataclass, field

@dataclass
class STTResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    duration_seconds: float = 0.0
    provider: str = ""
    metadata: dict = field(default_factory=dict)


class STTProvider:
    provider_id: str

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None
    ) -> STTResult:
        raise NotImplementedError

    def health(self) -> tuple[bool, str]:
        """
        Returns (is_healthy, status_message).
        """
        raise NotImplementedError

    def supported_formats(self) -> list[str]:
        raise NotImplementedError
