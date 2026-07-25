"""
LIVE JANUS / PHONETIC VARIANT SESSION PREFIX VERIFICATION HARNESS
================================================================
Verifies that phonetic variants ("janus", "wake up janus", "javis", "hey janus")
are cleanly resolved and stripped via TranscriptResolver in active sessions and passive mode.
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
print(f"LIVE PHONETIC VARIANT NORMALIZATION HARNESS STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.engine import JarvisEngine
from services.conversation.transcript_resolver import transcript_resolver

def run_normalization_harness():
    engine = JarvisEngine()
    engine.transition_to("SESSION_LISTENING")
    engine.in_session = True

    def pump_events(seconds=2.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    test_utterances = [
        "janus what is the time now",
        "wake up janus tell me a joke",
        "hey janus open calculator",
        "javish what causes rain",
        "jollis turn off computer"
    ]

    print("\n--- Testing Active Session Phonetic Variant Prefix Resolution ---")
    for text in test_utterances:
        resolved_tr = transcript_resolver.resolve(text, session_active=True)
        print(f"RAW: '{text}' -> WAKE MATCHED: {resolved_tr.wake_word_detected} ({resolved_tr.wake_word_position}) -> BODY: '{resolved_tr.resolved_text}'")
        engine.on_typed_command_received(text)
        pump_events(1.5)

    print("\n=" * 80)
    print("LIVE PHONETIC VARIANT NORMALIZATION HARNESS FINISHED")
    print("=" * 80)

if __name__ == "__main__":
    run_normalization_harness()
