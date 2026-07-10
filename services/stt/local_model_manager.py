import os
import threading
from core.config import config
from core.logger import logger

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

class LocalModelManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = LocalModelManager()
        return cls._instance

    def __init__(self):
        self.model = None
        self.loaded_model_size = None
        self.loaded_device = None
        self.loaded_compute_type = None
        self.load_lock = threading.Lock()

    def get_model(self):
        if not WHISPER_AVAILABLE:
            raise ImportError("faster-whisper package is not installed.")

        model_size = config.get("whisper_model", "small.en")
        device = config.get("whisper_device", "cpu")
        compute_type = config.get("whisper_compute_type", "int8")
        model_dir = config.get("whisper_model_path", "models/whisper")

        # Map auto to cpu if CUDA fails later
        with self.load_lock:
            if (self.model is None or 
                self.loaded_model_size != model_size or 
                self.loaded_device != device or 
                self.loaded_compute_type != compute_type):
                
                logger.info(f"Loading local faster-whisper model '{model_size}' (requested device={device}, compute={compute_type})...")
                try:
                    self.model = WhisperModel(
                        model_size,
                        device=device,
                        compute_type=compute_type,
                        download_root=model_dir
                    )
                    self.loaded_device = device
                    self.loaded_compute_type = compute_type
                except Exception as e:
                    logger.warn(f"Failed to load Faster-Whisper with requested device={device}, compute={compute_type}: {e}")
                    if device != "cpu" or compute_type != "int8":
                        logger.warn("CUDA unavailable or cublas missing. Retrying Faster-Whisper on CPU int8.")
                        self.model = WhisperModel(
                            model_size,
                            device="cpu",
                            compute_type="int8",
                            download_root=model_dir
                        )
                        self.loaded_device = "cpu"
                        self.loaded_compute_type = "int8"
                    else:
                        raise e
                        
                self.loaded_model_size = model_size
                logger.info(f"Local faster-whisper model loaded successfully on {self.loaded_device} ({self.loaded_compute_type}).")

            return self.model

    def force_cpu_int8_reload(self):
        """
        Force a reload of the Whisper model on CPU with int8 compute.
        Called when CUDA/cuBLAS fails during model.transcribe() at runtime,
        even though model loading succeeded earlier.
        """
        with self.load_lock:
            logger.warning("Forcing model reload on CPU int8 due to CUDA/cuBLAS runtime failure.")
            config.set("whisper_device", "cpu")
            config.set("whisper_compute_type", "int8")
            self.model = None
            self.loaded_device = None
            self.loaded_compute_type = None

local_model_manager = LocalModelManager.get_instance()
