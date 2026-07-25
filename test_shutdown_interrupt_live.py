"""
LIVE SHUTTING_DOWN INTERRUPT REJECTION HARNESS
=============================================
Reproduces exact live sequence:
1. Engine enters SHUTTING_DOWN state during farewell speech.
2. An incidental/noise speech_interrupted signal arrives.
3. Verifies that speech_interrupted is IGNORED and state stays SHUTTING_DOWN.
4. Verifies full_exit_requested is emitted when speech finishes.
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
print(f"LIVE SHUTTING_DOWN INTERRUPT HARNESS STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.engine import JarvisEngine
from core.event_bus import bus

def run_live_shutdown_interrupt_harness():
    engine = JarvisEngine()
    exit_signal_emitted = []

    def on_full_exit():
        exit_signal_emitted.append(True)
        print("SIGNAL RECEIVED: bus.full_exit_requested emitted!")

    bus.full_exit_requested.connect(on_full_exit)

    def pump_events(seconds=1.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    print("\n--- Step 1: Transition engine to SHUTTING_DOWN ---")
    engine.transition_to("SHUTTING_DOWN")
    print(f"Engine State: {engine.state}")
    assert engine.state == "SHUTTING_DOWN"

    print("\n--- Step 2: Fire speech_interrupted signal during SHUTTING_DOWN ---")
    engine.on_speech_interrupted()
    print(f"Post Interrupt Engine State: {engine.state}")
    assert engine.state == "SHUTTING_DOWN"

    print("\n--- Step 3: Complete farewell speech (on_speech_ended) ---")
    engine.on_speech_ended()
    pump_events(0.5)

    print(f"Full Exit Emitted: {len(exit_signal_emitted) > 0}")
    assert len(exit_signal_emitted) > 0

    print("\n=" * 80)
    print("LIVE SHUTTING_DOWN INTERRUPT HARNESS PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_live_shutdown_interrupt_harness()
