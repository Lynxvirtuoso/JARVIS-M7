import io
import requests
import json
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult

class OpenAISTTProvider(STTProvider):
    provider_id = "openai_stt"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None
    ) -> STTResult:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            api_key = config.get("openai_api_key", "").strip()

        if not api_key:
            logger.error("OpenAI STT unavailable: API key missing")
            raise ValueError("OpenAI STT: API key missing")

        # OpenAI STT model configuration (allow user high accuracy or gpt-4o-mini custom transcriber name)
        model = config.get("openai_stt_model", "whisper-1")
        if model in ["gpt-4o-mini-transcribe", "gpt-4o-transcribe"]:
            # Fallback to standard whisper-1 if custom name is just used for STT configuration mapping
            model = "whisper-1"
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        files = {
            "file": (f"audio.{audio_format}", audio_bytes, f"audio/{audio_format}")
        }
        
        prompt = (
            "This is a Windows assistant command. Common words include:\n"
            "Jarvis, open, close, launch, notepad, chrome, microsoft edge, edge, file explorer, calculator, VS Code, Spotify, volume, screenshot, sleep, exit app, full shutdown.\n"
            "Transcribe clearly. Do not repeat phrases."
        )
        if initial_prompt:
            prompt = initial_prompt + "\n" + prompt

        data = {
            "model": model,
            "prompt": prompt
        }
        if language:
            data["language"] = language
            
        logger.info(f"Sending audio to OpenAI STT API (model={model})...")
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"OpenAI STT API error: {response.status_code} - {response.text}")
            raise RuntimeError(f"OpenAI STT API error: {response.text}")
            
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
