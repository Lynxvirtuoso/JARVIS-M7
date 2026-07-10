import requests
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult

class DeepgramProvider(STTProvider):
    provider_id = "deepgram"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None
    ) -> STTResult:
        api_key = config.get("deepgram_api_key", "").strip()
        if not api_key:
            logger.error("Deepgram provider unavailable: API key missing")
            raise ValueError("Deepgram: API key missing")

        model = config.get("deepgram_model", "nova-2")
        
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": f"audio/{audio_format}"
        }
        
        params = {
            "model": model,
            "smart_format": "true",
            "language": language or "en",
            "punctuate": "true"
        }
        
        url = "https://api.deepgram.com/v1/listen"
        logger.info(f"Sending audio to Deepgram API (model={model})...")
        response = requests.post(url, headers=headers, params=params, data=audio_bytes, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Deepgram API error: {response.status_code} - {response.text}")
            raise RuntimeError(f"Deepgram API error: {response.text}")
            
        res_data = response.json()
        
        # Parse Deepgram response structure
        # { "results": { "channels": [ { "alternatives": [ { "transcript": "...", "confidence": 0.99 } ] } ] } }
        text = ""
        confidence = None
        try:
            alternatives = res_data["results"]["channels"][0]["alternatives"][0]
            text = alternatives["transcript"].strip()
            confidence = alternatives.get("confidence")
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Deepgram response: {e}")
            
        return STTResult(
            text=text,
            language=language,
            confidence=confidence,
            provider=self.provider_id,
            metadata=res_data
        )

    def health(self) -> tuple[bool, str]:
        api_key = config.get("deepgram_api_key", "").strip()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"

    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "m4a", "ogg", "flac"]
