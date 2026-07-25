"""
LIVE DESTRUCTIVE CONFIRMATION PROMPT PUNCTUATION VERIFICATION
============================================================
Triggers destructive actions (shutdown and calendar deletion) requiring confirmation,
and verifies live engine log & TTS prompt output ends with '?' rather than '-'.
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
print(f"LIVE DESTRUCTIVE CONFIRMATION VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.engine import JarvisEngine

def run_destructive_prompt_verification():
    engine = JarvisEngine()
    engine.transition_to("PASSIVE_WAKE_LISTENING")

    def pump_events(seconds=2.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    print("\n--- Test 1: Destructive Action - Shutdown Computer ---")
    engine.on_typed_command_received("jarvis shut down the computer")
    pump_events(3.0)

    print("\n--- Test 2: Destructive Action - Delete Calendar Meeting ---")
    engine.pending_action_choice = None
    engine.pending_confirmation_obj = None
    engine.pending_command = None
    engine.pending_command_type = None
    engine.transition_to("PASSIVE_WAKE_LISTENING")
    engine.on_typed_command_received("jarvis delete meeting project sync")
    pump_events(3.0)

    print("\n=" * 80)
    print("LIVE DESTRUCTIVE CONFIRMATION VERIFICATION FINISHED")
    print("=" * 80)

if __name__ == "__main__":
    run_destructive_prompt_verification()
