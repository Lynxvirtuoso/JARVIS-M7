"""
wake_model_manager.py -- Dedicated tiny.en Whisper model for fast wake-phrase detection.

Kept completely separate from local_model_manager (which handles command transcription)
so the tiny wake model and the larger command model can coexist without interference.
"""
import threading
from core.config import config
from core.logger import logger

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


class WakeModelManager:
    """
    Loads and caches a lightweight faster-whisper model (default: tiny.en) exclusively
    for wake-phrase detection. Uses beam_size=1 for minimum latency.
    """
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = WakeModelManager()
        return cls._instance

    def __init__(self):
        self.model = None
        self.loaded_model_size = None
        self.loaded_device = None
        self.load_lock = threading.Lock()

    def get_model(self):
        """Return the cached wake model, loading it if necessary."""
        if not WHISPER_AVAILABLE:
            raise ImportError("faster-whisper package is not installed.")

        # Wake model is intentionally separate from the command model config key
        model_size = config.get("wake_stt_model", "tiny.en")
        device = config.get("whisper_device", "cpu")
        model_dir = config.get("whisper_model_path", "models/whisper")

        with self.load_lock:
            if (
                self.model is None
                or self.loaded_model_size != model_size
                or self.loaded_device != device
            ):
                logger.info(
                    f"Loading wake detection model '{model_size}' on {device}..."
                )
                try:
                    self.model = WhisperModel(
                        model_size,
                        device=device,
                        compute_type="int8",   # Always int8 for wake -- fast and tiny
                        download_root=model_dir,
                    )
                    self.loaded_device = device
                except Exception as e:
                    logger.warning(
                        f"Wake model failed on {device}: {e}. Retrying on CPU int8."
                    )
                    self.model = WhisperModel(
                        model_size,
                        device="cpu",
                        compute_type="int8",
                        download_root=model_dir,
                    )
                    self.loaded_device = "cpu"

                self.loaded_model_size = model_size
                logger.info(
                    f"Wake model '{model_size}' loaded on {self.loaded_device}."
                )

        return self.model


# Module-level singleton
wake_model_manager = WakeModelManager.get_instance()
