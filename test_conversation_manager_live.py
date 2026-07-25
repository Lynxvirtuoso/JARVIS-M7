"""
LIVE CONVERSATION MANAGER VERIFICATION HARNESS
=============================================
Verifies state machine transitions, session-level idle timeouts,
interruption transitions, request_id staleness filtering, and public API.
"""

import sys
import os
import time
import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 80)
print(f"LIVE CONVERSATION MANAGER VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from services.conversation.conversation_manager import conversation_manager
from services.conversation.transcript_resolver import transcript_resolver
from services.conversation.models import ConversationState

def run_cm_live_verification():
    def pump_events(seconds=1.5):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    print("\n--- Step 1: Begin Session (Wake Triggered) ---")
    session = conversation_manager.begin_session("voice")
    print(f"Session Handle: {session.session_id} | State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.LISTENING

    print("\n--- Step 2: Handle Transcript -> THINKING -> SPEAKING ---")
    tr = transcript_resolver.resolve("janus what is the time now", session_active=True)
    req_id = "req-test-001"
    session.active_request_id = req_id

    conversation_manager.handle_transcript("janus what is the time now", tr)
    print(f"Post Handle Transcript State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.THINKING

    conversation_manager.notify_speech_started(req_id)
    print(f"Post Speech Started State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.SPEAKING

    print("\n--- Step 3: Stale Request Notification Rejection ---")
    conversation_manager.notify_speech_finished("stale-req-999")
    print(f"Post Stale Speech Finished State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.SPEAKING

    print("\n--- Step 4: Valid Speech Finished -> WAITING_FOR_FOLLOW_UP (Timer Active) ---")
    conversation_manager.notify_speech_finished(req_id)
    print(f"Post Valid Speech Finished State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.WAITING_FOR_FOLLOW_UP

    print("\n--- Step 5: Follow-Up Utterance -> LISTENING ---")
    tr_followup = transcript_resolver.resolve("what causes rain", session_active=True)
    req_id_2 = "req-test-002"
    session.active_request_id = req_id_2
    conversation_manager.handle_transcript("what causes rain", tr_followup)
    print(f"Post Follow-Up State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() in (ConversationState.THINKING, ConversationState.LISTENING)

    print("\n--- Step 6: Interruption Transition ---")
    conversation_manager.notify_speech_started(req_id_2)
    print(f"Speaking State: {conversation_manager.get_session_state().value}")
    conversation_manager.interrupt(req_id_2)
    print(f"Post Interrupt State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.INTERRUPTED

    print("\n--- Step 7: Session Idle Timeout ---")
    conversation_manager.notify_speech_finished(req_id_2)
    print(f"Waiting Follow-Up State: {conversation_manager.get_session_state().value}")
    print("Pumping events for 6.0 seconds to trigger session idle timeout...")
    pump_events(6.0)
    print(f"Post Idle Timeout State: {conversation_manager.get_session_state().value}")
    assert conversation_manager.get_session_state() == ConversationState.IDLE

    print("\n=" * 80)
    print("LIVE CONVERSATION MANAGER VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_cm_live_verification()
