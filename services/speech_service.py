import os
import threading
import queue
import time
from typing import Dict, Optional
from services.conversation.models import SpeechLifecycleState
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
        self.active_request_id: Optional[str] = None

        self._lifecycles: Dict[str, SpeechLifecycleState] = {}
        self._lifecycle_lock = threading.Lock()
        os.makedirs("models", exist_ok=True)

        # Start the background Synthesis Worker thread
        self.synthesis_worker = threading.Thread(target=self._synthesis_loop, daemon=True)
        self.synthesis_worker.start()

    @property
    def tts_cooldown_active(self):
        """Returns True if we are still in post-TTS cooldown to avoid self-hearing."""
        cooldown_ms = int(config.get("tts_mic_cooldown_ms", "800"))
        return (time.time() - self.speech_end_time) < (cooldown_ms / 1000.0)

    def begin_request(self, request_id: str) -> None:
        with self._lifecycle_lock:
            self.active_request_id = request_id
            # Prune old lifecycle entries to prevent unbounded memory retention
            if len(self._lifecycles) > 50:
                stale_keys = [k for k, v in self._lifecycles.items() if (v.speech_ended_emitted or v.cancelled) and k != request_id]
                for k in stale_keys:
                    del self._lifecycles[k]
            self._lifecycles[request_id] = SpeechLifecycleState(
                request_id=request_id,
                producer_finished=False,
                synthesis_active=0,
                queued_text_count=0,
                queued_audio_count=0,
                provider_playing=False,
                cancelled=False,
                speech_ended_emitted=False,
            )
        from services.tts.streaming_tts_queue import streaming_tts_queue
        streaming_tts_queue.start_new_request(request_id=request_id)

    def start_request(self, request_id: str) -> None:
        self.begin_request(request_id)

    def begin_stream(self, request_id: str) -> None:
        self.begin_request(request_id)

    def enqueue_stream_sentence(self, text: str, *, request_id: str) -> None:
        self.speak(text, request_id=request_id, standalone=False)

    def finish_stream(self, request_id: str) -> None:
        self.mark_producer_finished(request_id)

    def enqueue_sentence(self, text: str, *, request_id: str | None = None) -> None:
        self.speak(text, request_id=request_id, standalone=False)

    def speak_standalone(self, text: str, *, request_id: str | None = None) -> str:
        return self.speak(text, request_id=request_id, standalone=True)

    def mark_producer_finished(self, request_id: str) -> None:
        with self._lifecycle_lock:
            state = self._lifecycles.get(request_id)
            if state is None:
                return
            state.producer_finished = True

        self._check_and_emit_speech_ended(request_id)

    def cancel_request(self, request_id: str):
        with self._lifecycle_lock:
            state = self._lifecycles.get(request_id)
            if state:
                state.cancelled = True
        from services.tts.streaming_tts_queue import streaming_tts_queue
        streaming_tts_queue.cancel_request(request_id)

    def _check_and_emit_speech_ended(self, request_id: Optional[str] = None):
        should_emit = False
        with self._lifecycle_lock:
            req_id = request_id or self.active_request_id
            if not req_id:
                return

            state = self._lifecycles.get(req_id)
            if not state:
                return

            if state.speech_ended_emitted or state.cancelled:
                return

            # Never emit speech_ended while LLM producer stream is still producing text chunks
            if not state.producer_finished:
                return

            from services.tts.streaming_tts_queue import streaming_tts_queue
            if streaming_tts_queue.active_request_id and streaming_tts_queue.active_request_id != req_id:
                return

            is_idle = (
                not self.is_speaking
                and not state.provider_playing
                and state.synthesis_active == 0
                and state.queued_text_count == 0
                and state.queued_audio_count == 0
                and self.queue.empty()
                and self.audio_queue.empty()
            )

            if is_idle:
                state.speech_ended_emitted = True
                should_emit = True
                emit_req_id = req_id

        # Emit OUTSIDE the lock to prevent deadlocks from signal handlers
        if should_emit:
            logger.info(f"Speech playback fully completed for request {emit_req_id[:8]}. Emitting speech_ended.")
            try:
                bus.speech_ended.emit()
            except Exception as e:
                logger.warning(f"Bus speech_ended emission skipped (bus object invalidated): {e}")

    def speak(self, text, request_id: str | None = None, standalone: bool = True, begin_request: bool | None = None) -> str:
        from services.tts.sanitizer import sanitize_for_tts
        from core.telemetry import pipeline_timer, TelemetryContext
        import uuid
        sanitized = sanitize_for_tts(text) if text else ""

        should_begin = standalone if begin_request is None else begin_request
        req_id_str = request_id or f"sys-{uuid.uuid4().hex[:8]}"

        if not sanitized:
            if should_begin:
                self.begin_request(req_id_str)
            if standalone:
                self.mark_producer_finished(req_id_str)
            return req_id_str

        ctx = pipeline_timer.get_thread_context()
        if ctx is None:
            ctx = TelemetryContext(sanitized, request_id=req_id_str)
        else:
            ctx.request_id = req_id_str

        from services.tts.streaming_tts_queue import streaming_tts_queue
        if should_begin or (streaming_tts_queue.active_request_id != req_id_str):
            self.begin_request(req_id_str)
        else:
            with self._lifecycle_lock:
                if req_id_str not in self._lifecycles:
                    self._lifecycles[req_id_str] = SpeechLifecycleState(request_id=req_id_str)

        with self._lifecycle_lock:
            if req_id_str in self._lifecycles:
                self._lifecycles[req_id_str].queued_text_count += 1

        self.queue.put((sanitized, ctx))

        if standalone:
            self.mark_producer_finished(req_id_str)

        return req_id_str

    def stop(self):
        self.queue.put((None, None))
        self.audio_queue.put((None, None, None))

    def clear_queue(self):
        logger.info(f"Clearing text queue ({self.queue.qsize()}) and audio queue ({self.audio_queue.qsize()})")
        with self._lifecycle_lock:
            if self.active_request_id and self.active_request_id in self._lifecycles:
                self._lifecycles[self.active_request_id].cancelled = True
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
        from services.tts.streaming_tts_queue import streaming_tts_queue
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
                    self.queue.task_done()
                    continue

                req_id = getattr(ctx, "request_id", None)
                synthesis_started = False

                try:
                    # Check 1: Discard if request is stale before starting synthesis
                    if req_id and not streaming_tts_queue.is_request_active(req_id):
                        logger.info(f"[PIPELINE] Discarding stale text chunk before synthesis: '{text[:30]}...' for req {req_id[:8]}")
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                st = self._lifecycles[req_id]
                                st.queued_text_count = max(0, st.queued_text_count - 1)
                        continue

                    if req_id:
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                st = self._lifecycles[req_id]
                                st.queued_text_count = max(0, st.queued_text_count - 1)
                                st.synthesis_active += 1
                        synthesis_started = True

                    # Check 2: Discard if interrupted/stale right before TTS call
                    if tts_manager.interrupt_flag.is_set() or (req_id and not streaming_tts_queue.is_request_active(req_id)):
                        logger.info(f"[PIPELINE] Skipping TTS call for interrupted/stale request {req_id[:8] if req_id else 'None'}")
                        continue

                    logger.info(f"[PIPELINE] Synthesizing chunk in background: {text[:30]}...")
                    result = tts_manager.synthesize(text)

                    # Check 3: Discard post-synthesis if request was cancelled while generating
                    if tts_manager.interrupt_flag.is_set() or (req_id and not streaming_tts_queue.is_request_active(req_id)):
                        logger.info(f"[PIPELINE] Discarding synthesized chunk (stale/interrupted post-synthesis): {text[:30]}...")
                        continue

                    with self._lifecycle_lock:
                        if req_id and req_id in self._lifecycles:
                            self._lifecycles[req_id].queued_audio_count += 1
                    self.audio_queue.put((text, result, ctx))
                except Exception as e:
                    logger.error(f"[PIPELINE] Background synthesis failed for chunk: '{text[:30]}': {e}")
                    with self._lifecycle_lock:
                        if req_id and req_id in self._lifecycles:
                            self._lifecycles[req_id].queued_audio_count += 1
                    self.audio_queue.put((text, e, ctx))
                finally:
                    if synthesis_started and req_id:
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                st = self._lifecycles[req_id]
                                st.synthesis_active = max(0, st.synthesis_active - 1)
                    self.queue.task_done()
                    if req_id:
                        self._check_and_emit_speech_ended(req_id)
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in background synthesis loop: {e}", exc_info=True)

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        from services.tts.streaming_tts_queue import streaming_tts_queue

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

                req_id = getattr(ctx, "request_id", None)
                try:
                    if req_id:
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                st = self._lifecycles[req_id]
                                st.queued_audio_count = max(0, st.queued_audio_count - 1)

                    # Check 4: Discard audio before hardware playback if request is stale/cancelled
                    if tts_manager.interrupt_flag.is_set() or (req_id and not streaming_tts_queue.is_request_active(req_id)):
                        logger.info(f"[PIPELINE] Skipping playback for stale request {req_id[:8] if req_id else 'None'}")
                        continue

                    if isinstance(result, Exception):
                        logger.error(f"Skipping playback due to pre-synthesis error: {result}")
                        continue

                    self.is_speaking = True
                    if req_id:
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                self._lifecycles[req_id].provider_playing = True

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
                finally:
                    self.is_speaking = False
                    if req_id:
                        with self._lifecycle_lock:
                            if req_id in self._lifecycles:
                                self._lifecycles[req_id].provider_playing = False
                    self.current_spoken_sentence = ""
                    self.speech_end_time = time.time()
                    self.audio_queue.task_done()

                    # Post-playback check: only emit speech_ended if request remains active
                    if req_id and streaming_tts_queue.is_request_active(req_id):
                        self._check_and_emit_speech_ended(req_id)
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in speech playback loop: {e}", exc_info=True)


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

    def begin_request(self, request_id: str):
        self.engine.begin_request(request_id)

    def start_request(self, request_id: str):
        self.engine.start_request(request_id)

    def enqueue_sentence(self, text: str, *, request_id: str | None = None):
        self.engine.enqueue_sentence(text, request_id=request_id)

    def mark_producer_finished(self, request_id: str):
        self.engine.mark_producer_finished(request_id)

    def cancel_request(self, request_id: str):
        self.engine.cancel_request(request_id)

    def begin_stream(self, request_id: str):
        self.engine.begin_stream(request_id)

    def enqueue_stream_sentence(self, text: str, *, request_id: str):
        self.engine.enqueue_stream_sentence(text, request_id=request_id)

    def finish_stream(self, request_id: str):
        self.engine.finish_stream(request_id)

    def speak_standalone(self, text: str, *, request_id: str | None = None) -> str:
        logger.info(f"Speaking standalone: {text}")
        from core.telemetry import pipeline_timer
        pipeline_timer.log_event(f"TTS request sent: {text[:30]}...")
        if self.engine.queue.empty() and self.engine.audio_queue.empty():
            from services.tts.provider_manager import tts_manager
            tts_manager.clear_interrupt()
        return self.engine.speak_standalone(text, request_id=request_id)

    def speak(self, text, request_id: str | None = None, standalone: bool = True, begin_request: bool | None = None) -> str:
        logger.info(f"Speaking: {text}")
        from core.telemetry import pipeline_timer
        pipeline_timer.log_event(f"TTS request sent: {text[:30]}...")
        if self.engine.queue.empty() and self.engine.audio_queue.empty():
            from services.tts.provider_manager import tts_manager
            tts_manager.clear_interrupt()
        return self.engine.speak(text, request_id=request_id, standalone=standalone, begin_request=begin_request)

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
