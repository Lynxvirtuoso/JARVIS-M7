"""
LIVE TELEMETRY SCOPING HARNESS
==============================
Executes a multi-interaction lifecycle:
1. Wake detection + acknowledgement
2. Command execution ("jarvis turn off computer") -> triggers confirmation prompt
3. Confirmation response ("yes") -> triggers sensitive action
"""

import sys
import os
import time
import datetime
import traceback

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 80)
print(f"LIVE TELEMETRY SCOPING HARNESS STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.event_bus import bus
from core.engine import JarvisEngine

def run_telemetry_scoping_session():
    print("\n[HARNESS] Instantiating JarvisEngine...")
    try:
        engine = JarvisEngine()
        print("[HARNESS] JarvisEngine created successfully.")
    except Exception as e:
        print(f"[HARNESS ERROR] Engine creation failed: {e}")
        traceback.print_exc()
        return

    def pump_events(seconds=3.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    print("\n--- Interaction 1: Wake Detection + Acknowledgement ---")
    engine.on_wake_detected("voice")
    pump_events(2.0)

    print("\n--- Interaction 2: Command Execution (Shutdown Confirmation Prompt) ---")
    engine.on_typed_command_received("jarvis turn off computer")
    pump_events(3.0)

    print("\n--- Interaction 3: Confirmation Response ('yes') ---")
    engine.on_typed_command_received("yes")
    pump_events(3.0)

    print("\n=" * 80)
    print("LIVE TELEMETRY SCOPING HARNESS FINISHED")
    print("=" * 80)

if __name__ == "__main__":
    run_telemetry_scoping_session()
