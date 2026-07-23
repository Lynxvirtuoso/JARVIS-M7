import os
import requests
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult

def _load_api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return (os.getenv("GROQ_API_KEY") or config.get("groq_api_key", "")).strip()

class GroqSTTProvider(STTProvider):
    provider_id = "groq_stt"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None,
    ) -> STTResult:
        from services.groq_quota_manager import groq_quota_manager, ProviderUnavailable, extract_retry_delay_seconds

        stt_model = config.get("groq_stt_model", "whisper-large-v3-turbo")
        if not groq_quota_manager.is_available(stt_model, "stt"):
            remaining = groq_quota_manager.get_remaining_seconds(stt_model, "stt")
            raise ProviderUnavailable(f"Groq STT cooling down for {remaining}s")

        api_key = _load_api_key()
        if not api_key:
            raise ValueError("Groq API key missing for STT")

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        # Map formats
        mime_map = {
            "wav": "audio/wav",
            "mp3": "audio/mp3",
            "m4a": "audio/mp4",
            "webm": "audio/webm",
            "ogg": "audio/ogg",
            "flac": "audio/flac",
        }
        mime_type = mime_map.get(audio_format.lower(), f"audio/{audio_format}")
        
        filename = f"audio.{audio_format}"
        files = {
            "file": (filename, audio_bytes, mime_type)
        }
        data = {
            "model": stt_model,
            "temperature": "0.0"
        }
        if language:
            data["language"] = language
        if initial_prompt:
            data["prompt"] = initial_prompt
            logger.info(f"[DEBUG GROQ PROMPT] Sending initial_prompt to Groq: {initial_prompt!r}")

        logger.info(f"Requesting Groq STT transcription (model={stt_model})...")
        response = requests.post(url, headers=headers, files=files, data=data, timeout=20)

        if response.status_code != 200:
            error_text = response.text
            if response.status_code == 429:
                retry_seconds = extract_retry_delay_seconds(response.headers, error_text)
                logger.warning(f"Groq STT quota exceeded. Cooling down for {retry_seconds}s.")
                groq_quota_manager.set_cooldown(stt_model, retry_seconds, "stt")
                raise ProviderUnavailable(f"Groq STT quota exceeded. Cooling down for {retry_seconds}s")
            raise RuntimeError(f"Groq STT API error {response.status_code}: {error_text}")

        res_data = response.json()
        text = res_data.get("text", "").strip()

        logger.info(f"Groq STT transcription: {text!r}")
        return STTResult(
            text=text,
            language=language,
            provider=self.provider_id,
            metadata=res_data,
        )

    def health(self) -> tuple[bool, str]:
        api_key = _load_api_key()
        if not api_key:
            return False, "Unavailable: API key missing"
        from services.groq_quota_manager import groq_quota_manager
        stt_model = config.get("groq_stt_model", "whisper-large-v3-turbo")
        if not groq_quota_manager.is_available(stt_model, "stt"):
            remaining = groq_quota_manager.get_remaining_seconds(stt_model, "stt")
            return False, f"Groq STT is cooling down ({remaining}s remaining)"
        return True, "Ready"

    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "m4a", "webm", "ogg", "flac"]
