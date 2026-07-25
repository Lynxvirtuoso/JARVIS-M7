"""
test_conversation_manager.py
Unit test suite for Phase 2.1 ConversationManager.
Verifies state machine transitions, session handles, idle timeouts,
request_id staleness filtering, and public notifications.
"""

import unittest
import time
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from services.conversation.conversation_manager import ConversationManager
from services.conversation.models import ConversationState, ResolvedTranscript


class TestConversationManager(unittest.TestCase):

    def setUp(self):
        self.cm = ConversationManager(idle_timeout_seconds=0.5)

    def tearDown(self):
        if self.cm.active_session:
            self.cm.end_session("test_cleanup")

    def test_begin_and_end_session(self):
        session = self.cm.begin_session("voice")
        self.assertIsNotNone(session)
        self.assertEqual(self.cm.get_session_state(), ConversationState.LISTENING)
        self.assertEqual(self.cm.active_session.trigger_source, "voice")

        self.cm.end_session("user_close")
        self.assertEqual(self.cm.get_session_state(), ConversationState.IDLE)
        self.assertIsNone(self.cm.active_session)

    def test_state_transitions(self):
        session = self.cm.begin_session("wake_word")
        req_id = "req-101"
        session.active_request_id = req_id

        tr = ResolvedTranscript(
            raw_text="hello",
            resolved_text="hello",
            confidence=0.9,
            wake_word_detected=True,
        )
        self.cm.handle_transcript("hello", tr)
        self.assertEqual(self.cm.get_session_state(), ConversationState.THINKING)

        self.cm.notify_speech_started(req_id)
        self.assertEqual(self.cm.get_session_state(), ConversationState.SPEAKING)

        self.cm.notify_speech_finished(req_id)
        self.assertEqual(self.cm.get_session_state(), ConversationState.WAITING_FOR_FOLLOW_UP)

    def test_stale_request_id_ignored(self):
        session = self.cm.begin_session("wake_word")
        session.active_request_id = "req-current"

        tr = ResolvedTranscript(raw_text="hello", resolved_text="hello", confidence=0.9)
        self.cm.handle_transcript("hello", tr)
        self.cm.notify_speech_started("req-current")
        self.assertEqual(self.cm.get_session_state(), ConversationState.SPEAKING)

        # Stale notification should be ignored
        self.cm.notify_speech_finished("req-stale-999")
        self.assertEqual(self.cm.get_session_state(), ConversationState.SPEAKING)

    def test_interruption_flow(self):
        session = self.cm.begin_session("wake_word")
        req_id = "req-202"
        session.active_request_id = req_id

        tr = ResolvedTranscript(raw_text="test", resolved_text="test", confidence=0.9)
        self.cm.handle_transcript("test", tr)
        self.cm.notify_speech_started(req_id)
        self.assertEqual(self.cm.get_session_state(), ConversationState.SPEAKING)

        self.cm.interrupt(req_id)
        self.assertEqual(self.cm.get_session_state(), ConversationState.INTERRUPTED)

    def test_idle_timeout_closes_session(self):
        session = self.cm.begin_session("wake_word")
        req_id = "req-303"
        session.active_request_id = req_id

        tr = ResolvedTranscript(raw_text="test", resolved_text="test", confidence=0.9)
        self.cm.handle_transcript("test", tr)
        self.cm.notify_speech_started(req_id)
        self.cm.notify_speech_finished(req_id)
        self.assertEqual(self.cm.get_session_state(), ConversationState.WAITING_FOR_FOLLOW_UP)

        # Wait for short 0.5s idle timer
        start_t = time.time()
        while time.time() - start_t < 0.8:
            QCoreApplication.processEvents()
            time.sleep(0.05)

        self.assertEqual(self.cm.get_session_state(), ConversationState.IDLE)


if __name__ == "__main__":
    unittest.main()
