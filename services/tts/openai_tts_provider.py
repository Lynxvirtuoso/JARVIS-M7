import io
import requests
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult

class OpenAIWhisperTTSProvider(TTSProvider):
    provider_id = "openai_tts"

    def __init__(self):
        self.quota_exceeded = False

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
        api_key = config.get("openai_api_key", "").strip()
        if not api_key:
            logger.error("OpenAI TTS unavailable: API key missing")
            raise ValueError("OpenAI TTS: API key missing")

        model = config.get("openai_tts_model", "tts-1")
        voice = voice_id or config.get("openai_tts_voice") or config.get("tts_voice_id", "onyx")
        speed_val = speed or float(config.get("tts_speed", "1.0"))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # We request wav format for easy playing via soundfile/sounddevice
        data = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "speed": speed_val
        }
        
        logger.info(f"Sending request to OpenAI TTS API (model={model}, voice={voice})...")
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers=headers,
            json=data,
            timeout=15
        )
        
        if response.status_code != 200:
            if response.status_code == 429 or "insufficient_quota" in response.text:
                self.quota_exceeded = True
                logger.error("OpenAI TTS unavailable: insufficient quota. Falling back to next provider.")
            logger.error(f"OpenAI TTS API error: {response.status_code} - {response.text}")
            raise RuntimeError(f"OpenAI TTS API error: {response.text}")
            
        return TTSResult(
            audio=response.content,
            format="wav",
            sample_rate=24000, # OpenAI default wav samplerate is 24kHz
            provider=self.provider_id,
            voice_id=voice
        )

    def available_voices(self) -> list[str]:
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def health(self) -> tuple[bool, str]:
        if getattr(self, "quota_exceeded", False):
            return False, "Unavailable: insufficient quota"
        api_key = config.get("openai_api_key", "").strip()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"
