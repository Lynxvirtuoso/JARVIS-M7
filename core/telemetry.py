import time
import threading
from core.logger import logger

class TelemetryContext:
    def __init__(self, command: str):
        self.command = command
        self.start_time = time.time()
        self.events = []

class PipelineTimer:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PipelineTimer()
        return cls._instance

    def __init__(self):
        self._local = threading.local()
        self.active_playing_context = None

    def get_thread_context(self):
        return getattr(self._local, "current_context", None)

    def set_thread_context(self, ctx):
        self._local.current_context = ctx

    def reset(self):
        self._local.current_context = None
        self.active_playing_context = None

    def start_pipeline(self, command: str):
        ctx = TelemetryContext(command)
        self.set_thread_context(ctx)
        self.log_event("transcript received (STT complete)")

    def log_event(self, name: str):
        is_speech = "tts" in name.lower() or "playback" in name.lower() or "speech" in name.lower()
        
        if is_speech:
            ctx = self.active_playing_context or self.get_thread_context()
        else:
            ctx = self.get_thread_context() or self.active_playing_context

        if ctx is not None:
            elapsed = (time.time() - ctx.start_time) * 1000.0
            timestamp = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
            ctx.events.append((name, elapsed, timestamp))
            logger.info(f"[TELEMETRY] [{ctx.command}] Event: {name} | Elapsed: {elapsed:.2f} ms")
        else:
            logger.info(f"[TELEMETRY] [No Context] Event: {name}")

    def print_summary(self):
        ctx = self.active_playing_context or self.get_thread_context()
        if ctx is not None:
            logger.info(f"=== PIPELINE TELEMETRY SUMMARY FOR: {ctx.command} ===")
            for name, elapsed, ts in ctx.events:
                logger.info(f"   {name:<45} | {elapsed:>8.2f} ms | {ts}")
            logger.info("=========================================================")
            
            if ctx == self.active_playing_context:
                self.active_playing_context = None
            else:
                self.set_thread_context(None)
        else:
            logger.warning("=== PIPELINE TELEMETRY SUMMARY FOR: None ===")

pipeline_timer = PipelineTimer.get_instance()
