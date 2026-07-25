"""
TEST HARNESS FOR AUDIO SERVICE SILENCE DETECTION
=================================================
Instantiates AudioService and streams synthetic PCM chunks to verify:
1. Command recording stops via "Command silence detected" under 15s.
2. Passive wake buffer completes in < 3.2s on post-speech silence.
3. Continuous speech records without early cutoff.
"""

import sys
import os
import time
import numpy as np
import unittest.mock as mock

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

class MockEventBus:
    _instance = None
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    def __getattr__(self, name):
        mock_signal = mock.MagicMock()
        mock_signal.emit = mock.MagicMock()
        mock_signal.connect = mock.MagicMock()
        return mock_signal

sys.modules.setdefault("pyaudio", mock.MagicMock())
mock_bus_mod = mock.MagicMock()
mock_bus_mod.EventBus = MockEventBus
mock_bus_mod.bus = MockEventBus.get_instance()
sys.modules["core.event_bus"] = mock_bus_mod

from services.audio_service import audio_service

# Mock STT worker so background thread doesn't crash on unconfigured models
audio_service._transcribe_command = mock.MagicMock()
audio_service._check_wake_phrase = mock.MagicMock()

def generate_pcm_chunk(rms_level, chunk_size=1024):
    if rms_level <= 0:
        return b"\x00" * (chunk_size * 2)
    samples = np.sin(np.linspace(0, 2 * np.pi * 440, chunk_size)) * (rms_level * 32767 * 1.414)
    samples = np.clip(samples, -32768, 32767).astype(np.int16)
    return samples.tobytes()

def test_command_silence_detection():
    print("\n" + "=" * 70)
    print("TEST 1: Command Silence Detection (Speech followed by Silence)")
    print("=" * 70)

    audio_service.is_recording_command = True
    audio_service.command_has_speech = False
    audio_service.silence_counter = 0
    audio_service.command_buffer = []
    audio_service.pre_roll_buffer = []

    threshold = audio_service.silence_threshold
    timeout_chunks = audio_service.silence_timeout_chunks
    print(f"Active silence threshold: {threshold}, Timeout chunks: {timeout_chunks}")

    # 1. Speech chunks (RMS > threshold)
    speech_chunks = 20  # ~1.28s of speech
    speech_rms = threshold * 2.0
    for _ in range(speech_chunks):
        chunk = generate_pcm_chunk(rms_level=speech_rms)
        audio_service._process_command_recording(chunk, rms=speech_rms)

    print(f"Speech fed: {speech_chunks} chunks (~1.28s). Speech detected: {audio_service.command_has_speech}")
    print(f"Silence counter before silence: {audio_service.silence_counter}")

    # 2. Silence chunks (RMS < threshold)
    silence_fed = 0
    silence_rms = threshold * 0.1
    stop_reason = None
    for i in range(timeout_chunks + 10):
        chunk = generate_pcm_chunk(rms_level=silence_rms)
        audio_service._process_command_recording(chunk, rms=silence_rms)
        silence_fed += 1
        # Check buffer reset which happens on stop
        if len(audio_service.command_buffer) == 0 and audio_service.command_has_speech is False:
            stop_reason = "Command silence detected"
            break

    total_chunks = speech_chunks + silence_fed
    duration_sec = total_chunks * (1024 / 16000.0)

    print(f"Silence fed: {silence_fed} chunks (~{silence_fed * 0.064:.2f}s)")
    print(f"Total processed chunks: {total_chunks}")
    print(f"Total duration: {duration_sec:.2f}s")
    print(f"Stop reason: '{stop_reason}'")

    assert duration_sec < 15.0, f"Duration {duration_sec:.2f}s should be well under 15s"
    assert stop_reason == "Command silence detected", "Reason must match 'Command silence detected'"
    print("RESULT: PASS - Stopped via 'Command silence detected' in < 15s")

def test_wake_buffer_silence_completion():
    print("\n" + "=" * 70)
    print("TEST 2: Wake Buffer Completion (Wake phrase followed by silence)")
    print("=" * 70)

    audio_service.is_collecting_wake = False
    audio_service.wake_silence_counter = 0

    threshold = audio_service.wake_trigger_threshold

    # Trigger wake collection
    audio_service._process_passive_wake(generate_pcm_chunk(rms_level=threshold * 2.0), rms=threshold * 2.0)
    assert audio_service.is_collecting_wake, "Wake collection should be active"

    # Voice chunks (5 chunks ~0.32s)
    for _ in range(5):
        audio_service._process_passive_wake(generate_pcm_chunk(rms_level=threshold * 2.0), rms=threshold * 2.0)

    # Silence chunks until completion
    silence_chunks = 0
    silence_rms = threshold * 0.1
    for _ in range(25):
        if not audio_service.is_collecting_wake:
            break
        audio_service._process_passive_wake(generate_pcm_chunk(rms_level=silence_rms), rms=silence_rms)
        silence_chunks += 1

    dur = (1 + 5 + silence_chunks) * (1024 / 16000.0)
    print(f"Total wake buffer duration: {dur:.2f}s (Silence chunks before trigger: {silence_chunks})")
    print(f"Is collecting wake: {audio_service.is_collecting_wake}")

    assert not audio_service.is_collecting_wake, "Wake buffer collection should have completed"
    assert dur < 3.2, f"Wake buffer duration {dur:.2f}s should be under 3.2s cap"
    print("RESULT: PASS - Wake buffer completed on silence under 3.2s cap")

def test_continuous_speech_no_early_cutoff():
    print("\n" + "=" * 70)
    print("TEST 3: Continuous Speech No Early Cutoff")
    print("=" * 70)

    audio_service.is_recording_command = True
    audio_service.command_has_speech = False
    audio_service.silence_counter = 0
    audio_service.command_buffer = []
    audio_service.pre_roll_buffer = []

    threshold = audio_service.silence_threshold
    speech_rms = threshold * 2.0

    # 40 continuous speech chunks (RMS > threshold)
    for _ in range(40):
        chunk = generate_pcm_chunk(rms_level=speech_rms)
        audio_service._process_command_recording(chunk, rms=speech_rms)

    print(f"Silence counter during continuous speech: {audio_service.silence_counter}")
    print(f"Is recording command: {audio_service.is_recording_command}")

    assert audio_service.silence_counter == 0, "Silence counter should remain 0 during continuous speech"
    assert audio_service.is_recording_command, "Recording should remain active during continuous speech"
    print("RESULT: PASS - Continuous speech recorded without early cutoff")

if __name__ == "__main__":
    test_command_silence_detection()
    test_wake_buffer_silence_completion()
    test_continuous_speech_no_early_cutoff()
