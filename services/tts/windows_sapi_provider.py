import os
import tempfile
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult

try:
    import win32com.client
    import pythoncom
    SAPI_AVAILABLE = True
except ImportError:
    SAPI_AVAILABLE = False

class WindowsSapiProvider(TTSProvider):
    provider_id = "windows_sapi"

    def __init__(self):
        self.sapi_voice = None

    def stop_speaking(self):
        if self.sapi_voice:
            try:
                # 2 is SVSFPurgeBeforeSpeak (stops SAPI immediately)
                self.sapi_voice.Speak("", 2)
            except Exception as e:
                logger.error(f"Error interrupting SAPI: {e}")

    def _ensure_voice(self):
        if not SAPI_AVAILABLE:
            raise ImportError("pywin32 is not installed.")
        
        # Initialize COM in this thread
        pythoncom.CoInitialize()
        if self.sapi_voice is None:
            self.sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")

    def speak(self, text: str) -> None:
        self._ensure_voice()
        
        # Set speed rate (SAPI range: -10 to 10)
        # SAPI uses speech_rate (100-300, base 150) or tts_speed float slider (e.g. 1.0)
        speed_factor = float(config.get("tts_speed", "1.0"))
        rate = int(config.get("speech_rate", "180"))
        
        # Translate to SAPI rate scale (-10 to 10)
        if speed_factor != 1.0:
            # map speed_factor (0.5 to 2.0) to SAPI (-10 to 10)
            sapi_rate = int((speed_factor - 1.0) * 10)
        else:
            sapi_rate = max(-10, min(10, (rate - 150) // 10))
            
        self.sapi_voice.Rate = sapi_rate
        
        # Set voice if configured
        voice_id = config.get("tts_voice_id", "")
        if voice_id:
            for voice in self.sapi_voice.GetVoices():
                if voice.GetDescription() == voice_id:
                    self.sapi_voice.Voice = voice
                    break

        self.sapi_voice.Speak(text, 0)

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0
    ) -> TTSResult:
        self._ensure_voice()
        # For SAPI synthesis, we write to a temporary file using SAPI's file stream
        temp_wav = os.path.join(tempfile.gettempdir(), "sapi_temp.wav")
        
        fs = win32com.client.Dispatch("SAPI.SpFileStream")
        # 3 is SSFMCreateForWrite
        fs.Open(temp_wav, 3, False)
        
        old_stream = self.sapi_voice.AudioOutputStream
        self.sapi_voice.AudioOutputStream = fs
        
        # Set speed
        sapi_rate = int((speed - 1.0) * 10)
        self.sapi_voice.Rate = sapi_rate
        
        # Set voice
        v_id = voice_id or config.get("tts_voice_id", "")
        if v_id:
            for voice in self.sapi_voice.GetVoices():
                if voice.GetDescription() == v_id:
                    self.sapi_voice.Voice = voice
                    break

        self.sapi_voice.Speak(text, 0)
        fs.Close()
        
        # Restore stream
        self.sapi_voice.AudioOutputStream = old_stream
        
        with open(temp_wav, "rb") as f:
            audio_bytes = f.read()
            
        try:
            os.remove(temp_wav)
        except Exception:
            pass
            
        return TTSResult(
            audio=audio_bytes,
            format="wav",
            sample_rate=16000,
            provider=self.provider_id,
            voice_id=v_id
        )

    def available_voices(self) -> list[str]:
        try:
            self._ensure_voice()
            voices = []
            for voice in self.sapi_voice.GetVoices():
                voices.append(voice.GetDescription())
            return voices
        except Exception:
            return ["Default SAPI Voice"]

    def health(self) -> tuple[bool, str]:
        if not SAPI_AVAILABLE:
            return False, "Unavailable: package missing"
        try:
            self._ensure_voice()
            return True, "Ready"
        except Exception as e:
            return False, f"Failed: {str(e)}"
