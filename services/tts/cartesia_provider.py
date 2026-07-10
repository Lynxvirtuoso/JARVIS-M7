import io
import requests
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult

class CartesiaProvider(TTSProvider):
    provider_id = "cartesia"

    def speak(self, text: str) -> None:
        result = self.synthesize(text)
        
        import soundfile as sf
        import sounddevice as sd
        
        data, fs = sf.read(io.BytesIO(result.audio))
        sd.play(data, fs)
        sd.wait()

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0
    ) -> TTSResult:
        api_key = config.get("cartesia_api_key", "").strip()
        if not api_key:
            logger.error("Cartesia TTS unavailable: API key missing")
            raise ValueError("Cartesia TTS: API key missing")

        voice = voice_id or config.get("cartesia_voice_id") or config.get("tts_voice_id", "a0e99841-438c-4a64-b679-ae501e7d6091")
        
        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json"
        }
        
        # Cartesia body structure
        body = {
            "model_id": "sonic-english",
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice
            },
            "output_format": {
                "container": "wav",
                "encoding": "pcm_s16le",
                "sample_rate": 24000
            }
        }
        
        logger.info(f"Sending request to Cartesia TTS API (voice={voice})...")
        response = requests.post(
            "https://api.cartesia.ai/tts/bytes",
            headers=headers,
            json=body,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"Cartesia API error: {response.status_code} - {response.text}")
            raise RuntimeError(f"Cartesia API error: {response.text}")
            
        return TTSResult(
            audio=response.content,
            format="wav",
            sample_rate=24000,
            provider=self.provider_id,
            voice_id=voice
        )

    def available_voices(self) -> list[str]:
        # Return friendly voice IDs / names
        return [
            "a0e99841-438c-4a64-b679-ae501e7d6091", # British Butler
            "c8f7835e-28a3-4f0c-80d7-c1302ac62aae"  # Alistair British male
        ]

    def health(self) -> tuple[bool, str]:
        api_key = config.get("cartesia_api_key", "").strip()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"
