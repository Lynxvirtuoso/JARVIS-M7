import io
import requests
import json
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult

class OpenAIWhisperProvider(STTProvider):
    provider_id = "openai_whisper"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None
    ) -> STTResult:
        # First try to load from environment variable (which is populated from .env)
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = config.get("openai_api_key", "").strip()

        if not api_key:
            logger.error("OpenAI Whisper unavailable: API key missing")
            raise ValueError("OpenAI Whisper: API key missing")

        model = config.get("openai_stt_model", "whisper-1")
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        # We wrap the bytes in a file-like object
        files = {
            "file": (f"audio.{audio_format}", audio_bytes, f"audio/{audio_format}")
        }
        
        data = {
            "model": model
        }
        if language:
            data["language"] = language
        if initial_prompt:
            data["prompt"] = initial_prompt
            
        logger.info(f"Sending audio to OpenAI Whisper API (model={model})...")
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"OpenAI Whisper API error: {response.status_code} - {response.text}")
            raise RuntimeError(f"OpenAI Whisper API error: {response.text}")
            
        res_data = response.json()
        text = res_data.get("text", "").strip()
        
        return STTResult(
            text=text,
            language=language,
            provider=self.provider_id,
            metadata=res_data
        )

    def health(self) -> tuple[bool, str]:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = config.get("openai_api_key", "").strip()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"

    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "m4a", "webm", "mpga"]
