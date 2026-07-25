"""
services/conversation/conversation_manager.py
Phase 2.1 Conversation Manager for JARVIS M7.
Single owner of conversation sessions, idle-timeout behavior, follow-up detection,
and state transition coordination.
"""

import logging
import time
import uuid
from typing import Optional, Dict, Any, Set

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from services.conversation.models import (
    ConversationState,
    SessionHandle,
    ResolvedTranscript,
)

logger = logging.getLogger(__name__)


class ConversationManager(QObject):
    """
    Coordinates high-level conversation session lifetimes, idle timeouts, follow-up windows,
    and state transitions on the PyQt6 main event-loop thread.
    """

    session_started = pyqtSignal(object)  # SessionHandle
    session_ended = pyqtSignal(str, str)  # session_id, reason
    conversation_state_changed = pyqtSignal(str, str)  # old_state, new_state

    # Explicit State Transition Matrix
    ALLOWED_TRANSITIONS: Dict[ConversationState, Set[ConversationState]] = {
        ConversationState.IDLE: {ConversationState.LISTENING},
        ConversationState.LISTENING: {ConversationState.THINKING, ConversationState.WAITING_FOR_CONFIRMATION, ConversationState.CLOSING},
        ConversationState.THINKING: {ConversationState.SPEAKING, ConversationState.WAITING_FOR_CONFIRMATION, ConversationState.CLOSING},
        ConversationState.SPEAKING: {ConversationState.WAITING_FOR_FOLLOW_UP, ConversationState.INTERRUPTED, ConversationState.WAITING_FOR_CONFIRMATION, ConversationState.CLOSING},
        ConversationState.WAITING_FOR_CONFIRMATION: {ConversationState.LISTENING, ConversationState.CLOSING},
        ConversationState.INTERRUPTED: {ConversationState.LISTENING, ConversationState.WAITING_FOR_FOLLOW_UP, ConversationState.CLOSING},
        ConversationState.WAITING_FOR_FOLLOW_UP: {ConversationState.LISTENING, ConversationState.CLOSING},
        ConversationState.CLOSING: {ConversationState.IDLE},
    }

    def __init__(self, parent: Optional[QObject] = None, idle_timeout_seconds: float = 5.0):
        super().__init__(parent)
        self.state = ConversationState.IDLE
        self.active_session: Optional[SessionHandle] = None
        self.idle_timeout_ms = int(idle_timeout_seconds * 1000)

        # Single QTimer on main event-loop thread
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

    def transition_to(self, new_state: ConversationState) -> bool:
        """Enforces allowed state transitions and emits conversation_state_changed."""
        if self.state == new_state:
            return True

        allowed = self.ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            logger.warning(
                f"[CONVERSATION_MANAGER] Disallowed transition attempt: "
                f"{self.state.value} -> {new_state.value}. Ignored."
            )
            return False

        old_state = self.state
        self.state = new_state
        logger.info(
            f"[CONVERSATION_MANAGER] State transition: {old_state.value} -> {new_state.value}"
        )
        self.conversation_state_changed.emit(old_state.value, new_state.value)

        if new_state == ConversationState.CLOSING:
            self._complete_closing()

        return True

    def begin_session(self, trigger_source: str = "wake_word") -> SessionHandle:
        """Starts a new conversation session, resetting state to LISTENING."""
        if self.active_session is not None:
            self.end_session("new_session_override")

        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        self.active_session = SessionHandle(
            session_id=session_id,
            created_at=time.time(),
            trigger_source=trigger_source,
        )

        if self.state == ConversationState.IDLE:
            self.transition_to(ConversationState.LISTENING)
        else:
            self.state = ConversationState.LISTENING

        logger.info(f"[CONVERSATION_MANAGER] Session started: {session_id} (trigger: {trigger_source})")
        self.session_started.emit(self.active_session)
        return self.active_session

    def end_session(self, reason: str = "user_close") -> None:
        """Explicitly closes current conversation session and tears down timers."""
        if self.active_session is None:
            return

        self._idle_timer.stop()
        sess_id = self.active_session.session_id
        self.active_session = None

        if self.state != ConversationState.IDLE:
            self.transition_to(ConversationState.CLOSING)

        logger.info(f"[CONVERSATION_MANAGER] Session ended: {sess_id} (reason: {reason})")
        self.session_ended.emit(sess_id, reason)

    def _complete_closing(self) -> None:
        """Completes CLOSING -> IDLE transition."""
        self.transition_to(ConversationState.IDLE)

    def _on_idle_timeout(self) -> None:
        """Triggered when session idle timer expires in WAITING_FOR_FOLLOW_UP."""
        logger.info("[CONVERSATION_MANAGER] Session idle timer expired.")
        self.end_session("idle_timeout")

    def set_active_request(self, request_id: str) -> None:
        """Binds active_request_id to active session."""
        if self.active_session is not None:
            self.active_session.active_request_id = request_id

    def handle_transcript(self, transcript: str, resolved_result: ResolvedTranscript) -> None:
        """Receives normalized transcript and updates session state."""
        if self.active_session is None:
            self.begin_session("voice")

        self._idle_timer.stop()

        if self.state in (ConversationState.WAITING_FOR_FOLLOW_UP, ConversationState.INTERRUPTED):
            self.transition_to(ConversationState.LISTENING)

        if resolved_result.needs_clarification or resolved_result.is_sensitive_action:
            self.transition_to(ConversationState.WAITING_FOR_CONFIRMATION)
        else:
            self.transition_to(ConversationState.THINKING)

    @pyqtSlot(str)
    def notify_speech_started(self, request_id: str) -> None:
        """Subscribed from SpeechLifecycleState."""
        if not self._is_request_active(request_id):
            logger.debug(f"[CONVERSATION_MANAGER] Stale notify_speech_started ignored: {request_id}")
            return

        self._idle_timer.stop()
        if self.state == ConversationState.THINKING:
            self.transition_to(ConversationState.SPEAKING)

    @pyqtSlot(str)
    def notify_speech_finished(self, request_id: str) -> None:
        """Subscribed from SpeechLifecycleState."""
        if not self._is_request_active(request_id):
            logger.debug(f"[CONVERSATION_MANAGER] Stale notify_speech_finished ignored: {request_id}")
            return

        if self.state in (ConversationState.SPEAKING, ConversationState.INTERRUPTED):
            if self.transition_to(ConversationState.WAITING_FOR_FOLLOW_UP):
                self._idle_timer.start(self.idle_timeout_ms)

    @pyqtSlot(str, object)
    def notify_request_completed(self, request_id: str, result: Any = None) -> None:
        """Subscribed from request pipeline execution."""
        if not self._is_request_active(request_id):
            logger.debug(f"[CONVERSATION_MANAGER] Stale notify_request_completed ignored: {request_id}")
            return

        logger.info(f"[CONVERSATION_MANAGER] Request completed: {request_id}")

    @pyqtSlot(str)
    def interrupt(self, request_id: str) -> None:
        """Called by interruption detection pipeline."""
        if not self._is_request_active(request_id):
            logger.debug(f"[CONVERSATION_MANAGER] Stale interrupt ignored: {request_id}")
            return

        self._idle_timer.stop()
        if self.state == ConversationState.SPEAKING:
            self.transition_to(ConversationState.INTERRUPTED)

    def get_session_state(self) -> ConversationState:
        """Read-only query for diagnostics."""
        return self.state

    def _is_request_active(self, request_id: str) -> bool:
        """Validates request_id against active session."""
        if self.active_session is None:
            return False
        if not self.active_session.active_request_id:
            return True
        return self.active_session.active_request_id == request_id


# Global instance
conversation_manager = ConversationManager()
