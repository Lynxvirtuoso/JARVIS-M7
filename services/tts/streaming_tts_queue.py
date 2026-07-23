"""
services/tts/streaming_tts_queue.py
Ordered queue manager for sentence-level streaming TTS synthesis and playback.
Provides request-ID tracking, stale item filtering, backpressure, and immediate cancellation.
"""
import uuid
import queue
import threading
from dataclasses import dataclass
from core.logger import logger


@dataclass
class TTSStreamItem:
    request_id: str
    sequence: int
    text: str
    is_final: bool = False


class StreamingTTSQueue:
    """
    Manages an ordered, bounded queue of sentence items for continuous streaming speech.
    Supports active request ID validation, cancellation, and clean cleanup.
    """
    def __init__(self, max_size: int = 8):
        self.max_size = max(2, max_size)
        self._item_queue = queue.Queue(maxsize=self.max_size)
        self._active_request_id: str | None = None
        self._lock = threading.Lock()
        self._next_sequence = 0

    def start_new_request(self) -> str:
        """
        Generates a new unique request ID, invalidating previous request items and clearing pending queue items.
        """
        with self._lock:
            self._active_request_id = uuid.uuid4().hex
            self._next_sequence = 0
            self._clear_queue_unlocked()
            logger.info(f"[STREAMING TTS] Started new request ID: {self._active_request_id}")
            return self._active_request_id

    @property
    def active_request_id(self) -> str | None:
        with self._lock:
            return self._active_request_id

    def is_request_active(self, request_id: str) -> bool:
        with self._lock:
            return bool(request_id and self._active_request_id == request_id)

    def enqueue_sentence(self, request_id: str, text: str, is_final: bool = False) -> bool:
        """
        Puts a completed sentence into the streaming queue. Applies backpressure if full.
        Returns False if request is stale/cancelled.
        """
        if not text or not text.strip():
            return False

        with self._lock:
            if not self.is_request_active(request_id):
                logger.info(f"[STREAMING TTS] Rejected stale/cancelled sentence item for request {request_id}")
                return False
            seq = self._next_sequence
            self._next_sequence += 1

        item = TTSStreamItem(
            request_id=request_id,
            sequence=seq,
            text=text.strip(),
            is_final=is_final
        )

        try:
            # Put item into bounded queue with timeout to handle backpressure safely
            self._item_queue.put(item, timeout=5.0)
            logger.info(f"[STREAMING TTS] Enqueued sentence #{seq} for req {request_id[:8]}: '{text[:30]}...'")
            return True
        except queue.Full:
            logger.warning(f"[STREAMING TTS] Queue full ({self.max_size}), dropping sentence: '{text[:30]}...'")
            return False

    def get_next_item(self, timeout: float = 1.0) -> TTSStreamItem | None:
        """
        Fetches the next sentence item. Skips and discards stale request items.
        """
        try:
            item = self._item_queue.get(timeout=timeout)
            if item is None:
                return None

            with self._lock:
                if item.request_id != self._active_request_id:
                    logger.info(f"[STREAMING TTS] Skipping stale item seq #{item.sequence} (req {item.request_id[:8]})")
                    self._item_queue.task_done()
                    return None

            return item
        except queue.Empty:
            return None

    def task_done(self):
        try:
            self._item_queue.task_done()
        except ValueError:
            pass

    def cancel_active_request(self):
        """
        Cancels current request and clears all queued sentence items immediately.
        """
        with self._lock:
            logger.info(f"[STREAMING TTS] Cancelling active request ID: {self._active_request_id}")
            self._active_request_id = None
            self._next_sequence = 0
            self._clear_queue_unlocked()

    def _clear_queue_unlocked(self):
        try:
            while not self._item_queue.empty():
                self._item_queue.get_nowait()
                self._item_queue.task_done()
        except (queue.Empty, ValueError):
            pass


# Global streaming TTS queue instance
streaming_tts_queue = StreamingTTSQueue()
