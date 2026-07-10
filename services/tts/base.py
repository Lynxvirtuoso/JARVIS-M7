from dataclasses import dataclass, field

@dataclass
class TTSResult:
    audio: bytes
    format: str = "mp3"
    sample_rate: int = 24000
    duration_seconds: float = 0.0
    voice_id: str = ""
    provider: str = ""
    metadata: dict = field(default_factory=dict)


class TTSProvider:
    provider_id: str

    def speak(self, text: str) -> None:
        """
        Synthesize and play the text directly.
        Should handle playback internally.
        """
        raise NotImplementedError

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0
    ) -> TTSResult:
        """
        Synthesize text and return audio bytes.
        """
        raise NotImplementedError

    def available_voices(self) -> list[str]:
        raise NotImplementedError

    def health(self) -> tuple[bool, str]:
        """
        Returns (is_healthy, status_message).
        """
        raise NotImplementedError
