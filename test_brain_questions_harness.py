"""
LIVE QUESTIONS HARNESS FOR BRAIN-ROUTED COMMANDS
================================================
Executes 3 general brain-routed questions through the engine pipeline,
verifying that each question receives a complete response and speech output without cancellation.
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
print(f"LIVE BRAIN QUESTIONS HARNESS STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from core.event_bus import bus
from core.engine import JarvisEngine

speech_ended_events = []

def on_speech_ended():
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    speech_ended_events.append(timestamp)
    print(f"\n[{timestamp}] [EVENT] speech_ended emitted! Playback completed successfully.\n")

bus.speech_ended.connect(on_speech_ended)

def run_brain_questions_session():
    print("\n[HARNESS] Instantiating JarvisEngine...")
    try:
        engine = JarvisEngine()
        print("[HARNESS] JarvisEngine created successfully.")
    except Exception as e:
        print(f"[HARNESS ERROR] Engine creation failed: {e}")
        traceback.print_exc()
        return

    def pump_events(seconds=12.0):
        start_t = time.time()
        while time.time() - start_t < seconds:
            QCoreApplication.processEvents()
            time.sleep(0.1)

    questions = [
        ("1. General Question", "jarvis can you explain about football"),
        ("2. General Question", "jarvis what causes rain"),
        ("3. General Question", "jarvis tell me about quantum computing"),
    ]

    for label, q_text in questions:
        print("\n" + "=" * 70)
        print(f"TESTING COMMAND [{label}]: '{q_text}'")
        print("=" * 70)

        pre_ended_count = len(speech_ended_events)
        start_t = time.time()

        try:
            engine.on_typed_command_received(q_text)
            # Pump event loop for up to 12s per question to let LLM stream + TTS synthesize
            pump_events(12.0)
            duration = time.time() - start_t
            post_ended_count = len(speech_ended_events)

            print(f"  Execution duration: {duration:.2f}s")
            print(f"  New speech_ended events: {post_ended_count - pre_ended_count}")
            print(f"  Engine state after: {engine.state}")
            print(f"  Streamed fallback active: {getattr(engine, 'streamed_fallback_active', False)}")
        except Exception as e:
            print(f"  CRASHED: {e}")
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("LIVE BRAIN QUESTIONS HARNESS FINISHED")
    print(f"Total speech_ended events across run: {len(speech_ended_events)}")
    print("=" * 80)

if __name__ == "__main__":
    run_brain_questions_session()
