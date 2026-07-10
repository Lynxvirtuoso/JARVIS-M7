import io
import numpy as np
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult
from services.stt.local_model_manager import local_model_manager, WHISPER_AVAILABLE

# soundfile is imported lazily inside transcribe() to avoid hard crash if missing.


class LocalFasterWhisperProvider(STTProvider):
    provider_id = "local_faster_whisper"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None
    ) -> STTResult:
        import soundfile as sf  # Lazy import — avoid crash if soundfile is missing

        model = local_model_manager.get_model()

        # Read WAV bytes using soundfile
        audio_file = io.BytesIO(audio_bytes)
        data, samplerate = sf.read(audio_file)

        # Whisper model expects 16000Hz mono audio. Ensure it is float32
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)  # Convert stereo to mono
        data = data.astype(np.float32)

        # Resample if not 16000Hz
        if samplerate != 16000:
            duration = len(data) / samplerate
            xp = np.linspace(0, 1, len(data))
            x = np.linspace(0, 1, int(duration * 16000))
            data = np.interp(x, xp, data).astype(np.float32)

        # Stronger prompt — includes session prefix words and Windows assistant context
        default_prompt = (
            "This is a Windows desktop assistant command spoken by the user. "
            "The assistant is named Jarvis. Commands start with the word Jarvis "
            "(or Jervis, Javis, Charvis, Service). "
            "Common commands: Jarvis open Chrome, Jarvis open Notepad, Jarvis open VS Code, "
            "Jarvis close Jarvis, Jarvis sleep, Jarvis standby, Jarvis hide HUD, Jarvis exit app, "
            "Jarvis fully shutdown, Jarvis increase volume, Jarvis decrease volume, Jarvis mute volume, "
            "Jarvis take screenshot, Jarvis open file explorer, Jarvis open downloads, "
            "Jarvis what time is it, Jarvis play music, Jarvis stop music, Jarvis lock computer. "
            "Transcribe clearly, including the word Jarvis at the start."
        )
        prompt = initial_prompt or default_prompt

        # Config-driven transcription parameters for accent/quality tuning
        beam_size = int(config.get("stt_beam_size", "5"))
        temperature = float(config.get("stt_temperature", "0.0"))
        lang = language or config.get("stt_language", "en")

        transcribe_kwargs = dict(
            beam_size=beam_size,
            language=lang,
            temperature=temperature,
            condition_on_previous_text=False,
            vad_filter=True,
            initial_prompt=prompt,
        )

        try:
            segments, info = model.transcribe(data, **transcribe_kwargs)
        except Exception as e:
            # CUDA/cuBLAS can fail at inference time even if model loading succeeded.
            if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                logger.warning(
                    f"CUDA/cuBLAS failed during transcription: {e}. Retrying on CPU int8."
                )
                local_model_manager.force_cpu_int8_reload()
                model = local_model_manager.get_model()
                segments, info = model.transcribe(data, **transcribe_kwargs)
            else:
                raise

        transcription = " ".join([s.text for s in segments]).strip()

        return STTResult(
            text=transcription,
            language=info.language,
            confidence=getattr(info, 'language_probability', 1.0),
            duration_seconds=getattr(info, 'duration', 0.0),
            provider=self.provider_id
        )

    def health(self) -> tuple[bool, str]:
        """
        Health check must NOT load the Whisper model (it is heavy).
        Model loading happens lazily on first transcription call.
        """
        if not WHISPER_AVAILABLE:
            return False, "Unavailable: package missing"
        # Report ready without touching the model; the device/compute_type are shown
        # once the model has been loaded at least once.
        dev = local_model_manager.loaded_device
        comp = local_model_manager.loaded_compute_type
        if dev and comp:
            return True, f"Ready ({dev.upper()} {comp.upper()})"
        return True, "Ready / lazy load"

    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "flac", "ogg"]
