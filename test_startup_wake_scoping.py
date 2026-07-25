"""
LIVE VERIFICATION FOR STARTUP GREETING + WAKE ACKNOWLEDGEMENT SCOPING
====================================================================
Reproduces the exact original sequence:
1. Engine startup greeting speaks ("Good evening, Sir. Systems online...")
2. Wait 3.0 seconds idle in PASSIVE_WAKE_LISTENING mode.
3. Trigger wake detection ("voice") -> "Yes, Sir." acknowledgement speaks.
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
print(f"LIVE STARTUP GREETING + WAKE ACKNOWLEDGEMENT TEST STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.engine import JarvisEngine

def run_verification():
    def pump_events(seconds=3.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    print("\n--- Step 1: Instantiating JarvisEngine & Triggering Startup Greeting ---")
    engine = JarvisEngine()
    engine.start(startup_mode=False)
    pump_events(3.0)

    print("\n--- Step 2: Waiting 3.0 Seconds Idle in PASSIVE_WAKE_LISTENING ---")
    time.sleep(3.0)
    pump_events(1.0)

    print("\n--- Step 3: Triggering Wake Detection ('Yes, Sir.' Acknowledgement) ---")
    engine.on_wake_detected("voice")
    pump_events(3.0)

    print("\n=" * 80)
    print("LIVE STARTUP GREETING + WAKE ACKNOWLEDGEMENT TEST FINISHED")
    print("=" * 80)

if __name__ == "__main__":
    run_verification()
