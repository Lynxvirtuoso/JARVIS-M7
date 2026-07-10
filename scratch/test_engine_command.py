import sys
sys.path.append(r"d:\JARVIS M7")
from core.engine import JarvisEngine
from core.config import config
from core.trust_gate import TrustGate, ToolCall

engine = JarvisEngine()

print("Testing command normalization...")
print("Normalizing 'Jarvis, enable autostart' ->", engine.CommandWorker.normalize_command("Jarvis, enable autostart"))

print("\nTriggering _process_received_command with 'enable autostart'...")
# We can mock the speech and worker systems
import unittest.mock as mock

with mock.patch("core.engine.speech") as mock_speech, \
     mock.patch.object(engine, "_launch_worker") as mock_launch:
     
    # Ensure is_low_confidence is False
    engine._process_received_command("enable autostart", source="typed")
    
    print("State transitioned to:", engine.state)
    print("Worker launch called with:", mock_launch.call_args)
    print("Speech speak called with:", mock_speech.speak.call_args)
