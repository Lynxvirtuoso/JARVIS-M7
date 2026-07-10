import os
import subprocess
import tempfile
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult

class PiperProvider(TTSProvider):
    provider_id = "piper"

    def _get_paths(self):
        exe_path = config.get("piper_executable_path") or config.get("piper_exe_path", "piper/piper.exe")
        model_path = config.get("piper_model_path") or config.get("piper_model_path_old", "piper/en_US-lessac-medium.onnx")
        config_path = config.get("piper_config_path", "")
        return exe_path, model_path, config_path

    def speak(self, text: str) -> None:
        result = self.synthesize(text)
        
        # Play the synthesized audio
        import soundfile as sf
        import sounddevice as sd
        import io
        
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
        exe_path, model_path, config_path = self._get_paths()
        
        if not os.path.exists(exe_path) or not os.path.exists(model_path):
            raise FileNotFoundError("Piper executable or model file not found.")

        # Create temporary file for output
        temp_wav = os.path.join(tempfile.gettempdir(), "piper_temp.wav")
        cmd = [exe_path, "-m", model_path, "-f", temp_wav]
        
        if config_path and os.path.exists(config_path):
            cmd.extend(["-c", config_path])
            
        # Optional: speed scaling if piper supports it via length scale parameter
        # Piper parameter: --length_scale (default 1.0, lower is faster)
        # speed 1.0 -> length_scale 1.0
        # speed 1.2 -> length_scale 0.83
        if speed != 1.0 and speed > 0:
            cmd.extend(["--length_scale", str(round(1.0 / speed, 2))])

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        proc.communicate(input=text.encode('utf-8'))
        
        if not os.path.exists(temp_wav):
            raise RuntimeError("Piper synthesis failed to produce audio file.")
            
        with open(temp_wav, "rb") as f:
            audio_bytes = f.read()
            
        try:
            os.remove(temp_wav)
        except Exception:
            pass
            
        return TTSResult(
            audio=audio_bytes,
            format="wav",
            sample_rate=22050, # Typical default for Lessac medium
            provider=self.provider_id
        )

    def available_voices(self) -> list[str]:
        # Return currently active model name
        _, model_path, _ = self._get_paths()
        if model_path:
            return [os.path.basename(model_path)]
        return ["Default Piper Voice"]

    def health(self) -> tuple[bool, str]:
        exe_path, model_path, _ = self._get_paths()
        if not exe_path or not model_path:
            return False, "Unavailable: invalid config"
        if not os.path.exists(exe_path):
            return False, "Unavailable: package missing"
        if not os.path.exists(model_path):
            return False, "Unavailable: model missing"
        return True, "Ready"
