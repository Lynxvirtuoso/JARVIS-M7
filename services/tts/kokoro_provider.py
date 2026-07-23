import os
import io
import time
# soundfile is imported lazily inside methods to avoid hard crash if the package is missing.
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult


try:
    import kokoro_onnx
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

class KokoroProvider(TTSProvider):
    provider_id = "kokoro"

    def __init__(self):
        self.kokoro = None
        self.loaded_model_path = None
        self.loaded_voices_path = None
        self.phrase_cache = {}

        # Start background warmup and pre-caching
        import threading
        threading.Thread(target=self._warmup_background, daemon=True).start()

    def _warmup_background(self):
        try:
            self._ensure_kokoro()
            self.pre_cache_phrases()
        except Exception as e:
            logger.error(f"Error during background TTS warmup: {e}")

    def pre_cache_phrases(self) -> None:
        if os.getenv("JARVIS_TESTING") == "1":
            return
        static_phrases = [
            "Yes, Sir.",
            "Going passive, Sir.",
            "Shutting down fully, Sir.",
            "Command cancelled, Sir.",
            "Request cancelled, Sir.",
            "Systems online, Sir.",
            "Let me look into that, Sir.",
            "One moment, Sir.",
            "Searching now, Sir.",
            "Allow me to think about that, Sir."
        ]
        logger.info("Pre-synthesizing and caching static TTS phrases...")
        for phrase in static_phrases:
            try:
                # Pre-synthesize and store results
                self.phrase_cache[phrase] = self.synthesize(phrase)
                logger.info(f"Cached phrase: '{phrase}'")
            except Exception as e:
                logger.error(f"Failed to pre-cache phrase '{phrase}': {e}")

    def _ensure_kokoro(self):
        if not KOKORO_AVAILABLE:
            raise ImportError("kokoro-onnx package is not installed.")
            
        model_path = config.get("kokoro_model_path", "models/kokoro-v0.19.onnx")
        voices_path = config.get("kokoro_voices_path", "models/voices.bin")
        
        if not os.path.exists(model_path) or not os.path.exists(voices_path):
            raise FileNotFoundError(f"Kokoro model or voices file not found. Paths: model={model_path}, voices={voices_path}")
            
        if self.kokoro is None or self.loaded_model_path != model_path or self.loaded_voices_path != voices_path:
            logger.info("Initializing Kokoro ONNX engine with limited threads (4)...")
            
            import onnxruntime as ort
            original_init = ort.InferenceSession.__init__
            
            def patched_init(session_self, *args, **kwargs):
                if "sess_options" not in kwargs or kwargs["sess_options"] is None:
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 4
                    opts.inter_op_num_threads = 4
                    kwargs["sess_options"] = opts
                else:
                    kwargs["sess_options"].intra_op_num_threads = 4
                    kwargs["sess_options"].inter_op_num_threads = 4
                original_init(session_self, *args, **kwargs)
                
            ort.InferenceSession.__init__ = patched_init
            try:
                self.kokoro = kokoro_onnx.Kokoro(model_path, voices_path)
            finally:
                ort.InferenceSession.__init__ = original_init

            self.loaded_model_path = model_path
            self.loaded_voices_path = voices_path
            logger.info("Kokoro ONNX engine initialized successfully.")

    def speak(self, text: str) -> None:
        import time
        t0 = time.time()
        logger.info(f"[TIMING] Kokoro TTS - Starting synthesis for: {text!r}")

        result = self.synthesize(text)

        t1 = time.time()
        logger.info(f"[TIMING] Kokoro TTS - Synthesis finished in {t1 - t0:.4f}s")

        import soundfile as sf  # Lazy import
        import sounddevice as sd
        from services.tts.provider_manager import tts_manager

        data, fs = sf.read(io.BytesIO(result.audio), dtype='float32')
        
        chunk_size = int(fs * 0.15)  # 150ms chunks
        channels = 1 if len(data.shape) == 1 else data.shape[1]
        interrupted = False

        from core.telemetry import pipeline_timer
        pipeline_timer.log_event("TTS audio starts playing")
        with sd.OutputStream(samplerate=fs, channels=channels, dtype='float32') as stream:
            for i in range(0, len(data), chunk_size):
                if tts_manager.interrupt_flag.is_set():
                    interrupted = True
                    break
                chunk = data[i:i+chunk_size]
                stream.write(chunk)

        if interrupted:
            logger.info("Kokoro playback halted due to interrupt.")

        t2 = time.time()
        logger.info(f"[TIMING] Kokoro TTS - Playback finished. Playback took {t2 - t1:.4f}s. Total time: {t2 - t0:.4f}s")

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0
    ) -> TTSResult:
        voice = voice_id or config.get("kokoro_voice") or config.get("tts_voice_id") or "bm_daniel"
        speed_val = speed or float(config.get("tts_speed", "1.0"))

        # Check cache if parameters match defaults
        if text in self.phrase_cache:
            cached_res = self.phrase_cache[text]
            if cached_res.voice_id == voice:
                default_speed = float(config.get("tts_speed", "1.0"))
                if abs(speed_val - default_speed) < 0.01:
                    logger.info(f"TTS cache hit for: '{text}'")
                    return cached_res

        self._ensure_kokoro()
        # Ensure voice suffix or mapping is correct if required by kokoro-onnx
        
        t_start = time.time()
        samples, sample_rate = self.kokoro.create(
            text,
            voice=voice,
            speed=speed_val,
            lang="en-us"
        )
        t_end = time.time()
        logger.info(f"[TIMING] Kokoro ONNX Inference ONLY: {t_end - t_start:.4f}s for text: {text!r}")

        # Write samples to wav bytes
        import soundfile as sf  # Lazy import
        wav_io = io.BytesIO()
        sf.write(wav_io, samples, sample_rate, format='WAV', subtype='PCM_16')
        audio_bytes = wav_io.getvalue()
        
        return TTSResult(
            audio=audio_bytes,
            format="wav",
            sample_rate=sample_rate,
            provider=self.provider_id,
            voice_id=voice
        )

    def available_voices(self) -> list[str]:
        # All 54 voices in voices-v1.0.bin
        return [
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            "ef_dora", "em_alex", "em_santa", "ff_siwis",
            "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
            "if_sara", "im_nicola",
            "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
            "pf_dora", "pm_alex", "pm_santa",
            "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"
        ]

    def health(self) -> tuple[bool, str]:
        if not KOKORO_AVAILABLE:
            return False, "Unavailable: package missing"
        model_path = config.get("kokoro_model_path", "models/kokoro-v0.19.onnx")
        voices_path = config.get("kokoro_voices_path", "models/voices.bin")
        if not os.path.exists(model_path) or not os.path.exists(voices_path):
            return False, "Unavailable: model missing"
        try:
            self._ensure_kokoro()
            return True, "Ready"
        except Exception as e:
            return False, f"Failed: {str(e)}"
