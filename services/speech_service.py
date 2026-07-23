import os
import threading
import queue
import time
from core.event_bus import bus
from core.logger import logger
from core.config import config
from services.tts.provider_manager import tts_manager


# Windows-native COM dispatcher
try:
    import win32com.client
    SAPI_AVAILABLE = True
except ImportError:
    SAPI_AVAILABLE = False

class SpeechEngine(threading.Thread):
    """
    Background thread to queue and speak text.
    Ensures speech calls never block the main PyQt6 GUI thread.
    Exposes `is_speaking` so the audio service can mute mic processing during TTS.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.queue = queue.Queue()       # Text queue
        self.audio_queue = queue.Queue() # Pre-synthesized audio queue
        self.sapi_voice = None
        self.is_speaking = False
        self.current_spoken_sentence = ""
        self.recent_spoken_sentences = []
        self.speech_end_time = 0.0  # timestamp when last speech ended
        self.warned_kokoro = False
        self.warned_piper = False
        os.makedirs("models", exist_ok=True)

        # Start the background Synthesis Worker thread
        self.synthesis_worker = threading.Thread(target=self._synthesis_loop, daemon=True)
        self.synthesis_worker.start()

    @property
    def tts_cooldown_active(self):
        """Returns True if we are still in post-TTS cooldown to avoid self-hearing."""
        cooldown_ms = int(config.get("tts_mic_cooldown_ms", "800"))
        return (time.time() - self.speech_end_time) < (cooldown_ms / 1000.0)

    def speak(self, text, request_id: str | None = None):
        from services.tts.sanitizer import sanitize_for_tts
        from core.telemetry import pipeline_timer, TelemetryContext
        import uuid
        sanitized = sanitize_for_tts(text) if text else ""
        if not sanitized:
            return
        ctx = pipeline_timer.get_thread_context()
        if ctx is None:
            req_id = request_id or f"sys-{uuid.uuid4().hex[:8]}"
            ctx = TelemetryContext(sanitized, request_id=req_id)
        elif request_id:
            ctx.request_id = request_id

        req_id_str = getattr(ctx, "request_id", None)
        self.active_request_id = req_id_str
        if req_id_str:
            from services.tts.streaming_tts_queue import streaming_tts_queue
            streaming_tts_queue._active_request_id = req_id_str
        self.queue.put((sanitized, ctx))

    def stop(self):
        self.queue.put((None, None))
        self.audio_queue.put((None, None, None))

    def clear_queue(self):
        logger.info(f"Clearing text queue ({self.queue.qsize()}) and audio queue ({self.audio_queue.qsize()})")
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
        except queue.Empty:
            pass
            
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except queue.Empty:
            pass
        logger.info("Queues cleared successfully.")

    def _synthesis_loop(self):
        """Background thread to pre-synthesize text to audio chunks as they arrive in the queue."""
        while True:
            try:
                item = self.queue.get(timeout=1.0)
                if item is None:
                    break
                if isinstance(item, tuple):
                    text, ctx = item
                else:
                    text, ctx = item, None

                if text is None:
                    break
                if not text:
                    continue
                
                # If we are already interrupted, skip synthesis
                if tts_manager.interrupt_flag.is_set():
                    self.queue.task_done()
                    continue
                
                try:
                    logger.info(f"[PIPELINE] Synthesizing chunk in background: {text[:30]}...")
                    # Synthesize text to WAV bytes
                    result = tts_manager.synthesize(text)
                    
                    # If interrupted during synthesis, discard the result
                    if tts_manager.interrupt_flag.is_set():
                        logger.info(f"[PIPELINE] Discarding synthesized chunk due to interrupt: {text[:30]}...")
                        self.queue.task_done()
                        continue
                        
                    self.audio_queue.put((text, result, ctx))
                except Exception as e:
                    logger.error(f"[PIPELINE] Background synthesis failed for chunk: '{text[:30]}': {e}")
                    # Push error to playback queue so it logs and skips
                    self.audio_queue.put((text, e, ctx))
                
                self.queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in background synthesis loop: {e}", exc_info=True)

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        
        if SAPI_AVAILABLE:
            try:
                self.sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
                logger.info("Background thread SAPI voice engine initialized successfully.")
            except Exception as e:
                logger.error(f"Background thread SAPI initialization failed: {e}")

        while True:
            try:
                item = self.audio_queue.get(timeout=1.0)
                if item is None:
                    logger.info("Speech engine thread stopping...")
                    break
                
                if isinstance(item, tuple) and len(item) == 3:
                    text, result, ctx = item
                else:
                    text, result, ctx = item[0], item[1], None
                
                if text is None:
                    logger.info("Speech engine thread stopping...")
                    break
                
                # Check interrupt flag before starting playback
                if tts_manager.interrupt_flag.is_set():
                    self.audio_queue.task_done()
                    continue
                
                if isinstance(result, Exception):
                    logger.error(f"Skipping playback due to pre-synthesis error: {result}")
                    self.audio_queue.task_done()
                    continue
                
                self.is_speaking = True
                self.current_spoken_sentence = text
                self.recent_spoken_sentences.append(text)
                if len(self.recent_spoken_sentences) > 5:
                    self.recent_spoken_sentences.pop(0)

                bus.speech_started.emit(text)
                
                from core.telemetry import pipeline_timer
                if ctx is not None:
                    pipeline_timer.active_playing_context = ctx
                pipeline_timer.log_event(f"TTS playing pre-synthesized chunk: {text[:30]}...")
                
                # Play the pre-synthesized audio chunk
                tts_manager.play_result(result)
                
                self.is_speaking = False
                self.current_spoken_sentence = ""
                self.speech_end_time = time.time()
                self.audio_queue.task_done()
                if self.audio_queue.empty() and self.queue.empty():
                    bus.speech_ended.emit()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in speech playback loop: {e}", exc_info=True)
                self.is_speaking = False
                self.speech_end_time = time.time()
                if self.audio_queue.empty() and self.queue.empty():
                    bus.speech_ended.emit()

# Global speech service manager
class SpeechService:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SpeechService()
        return cls._instance
        
    def __init__(self):
        self.engine = SpeechEngine()
        self.engine.start()

    @property
    def is_speaking(self):
        return self.engine.is_speaking

    @property
    def current_spoken_sentence(self):
        return self.engine.current_spoken_sentence

    @property
    def recent_spoken_sentences(self):
        return self.engine.recent_spoken_sentences

    @property
    def tts_cooldown_active(self):
        return self.engine.tts_cooldown_active

    def speak(self, text):
        logger.info(f"Speaking: {text}")
        from core.telemetry import pipeline_timer
        pipeline_timer.log_event(f"TTS request sent: {text[:30]}...")
        # Clear interrupt flag on fresh responses (when both queues are empty)
        if self.engine.queue.empty() and self.engine.audio_queue.empty():
            from services.tts.provider_manager import tts_manager
            tts_manager.clear_interrupt()
        self.engine.speak(text)

    def clear_queue(self):
        self.engine.clear_queue()

    def stop(self):
        try:
            self.engine.stop()
            if self.engine.is_alive():
                self.engine.join(timeout=2.0)
            logger.info("Speech service stopped successfully.")
        except Exception as e:
            logger.warning(f"SpeechService stop cleanup warning: {e}")

speech = SpeechService.get_instance()

