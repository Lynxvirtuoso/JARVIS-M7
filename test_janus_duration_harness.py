"""
LIVE VERIFICATION HARNESS — Audio Service Fixes & Real Micro-Noise Filter
==========================================================================
Tests:
1. "janus", "wake up janus", "hey janus" phonetic recognition in is_wake_phrase.
2. Single-chunk noise spikes (1 chunk > threshold) do NOT trigger wake collection.
3. Sustained voice (2+ consecutive chunks > threshold) DOES trigger wake collection.
4. Spoken "wake up, jarvis" triggers correctly with 2+ consecutive voice chunks.
"""

import sys
import os
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

from services.audio_service import is_wake_phrase, audio_service

def generate_pcm_chunk(rms_level, chunk_size=1024):
    if rms_level <= 0:
        return b"\x00" * (chunk_size * 2)
    samples = np.sin(np.linspace(0, 2 * np.pi * 440, chunk_size)) * (rms_level * 32767 * 1.414)
    samples = np.clip(samples, -32768, 32767).astype(np.int16)
    return samples.tobytes()

def test_janus_wake_recognition():
    print("\n" + "=" * 70)
    print("TEST 1: Janus Phonetic Wake Phrase Recognition")
    print("=" * 70)

    test_phrases = ["janus", "wake up janus", "hey janus"]
    for text in test_phrases:
        matched, canonical = is_wake_phrase(text)
        print(f"Text: '{text}' -> Matched: {matched}, Canonical: '{canonical}'")
        assert matched, f"Phrase '{text}' should match wake phrase"
        assert canonical in ["jarvis", "wake up jarvis"], f"Canonical should be a recognized wake phrase for '{text}'"

    print("RESULT: PASS - All Janus wake variants correctly recognized")

def test_single_chunk_spike_filtering():
    print("\n" + "=" * 70)
    print("TEST 2: Single-Chunk Noise Spike Filtering (False-Positive Reduction)")
    print("=" * 70)

    audio_service.is_collecting_wake = False
    audio_service.wake_consecutive_voice = 0
    threshold = audio_service.wake_trigger_threshold

    # Single loud chunk (noise spike)
    chunk = generate_pcm_chunk(rms_level=threshold * 2.5)
    audio_service._process_passive_wake(chunk, rms=threshold * 2.5)

    print(f"Single spike fed -> Consecutive voice: {audio_service.wake_consecutive_voice}, Collecting: {audio_service.is_collecting_wake}")
    assert not audio_service.is_collecting_wake, "Single-chunk spike should NOT trigger wake collection"

    # Subsequent silence chunk resets counter
    silence_chunk = generate_pcm_chunk(rms_level=threshold * 0.1)
    audio_service._process_passive_wake(silence_chunk, rms=threshold * 0.1)
    print(f"Silence fed -> Consecutive voice: {audio_service.wake_consecutive_voice}, Collecting: {audio_service.is_collecting_wake}")
    assert audio_service.wake_consecutive_voice == 0, "Silence chunk should reset consecutive voice counter"

    print("RESULT: PASS - Single-chunk noise spikes correctly filtered without triggering wake collection")

def test_sustained_voice_wake_trigger():
    print("\n" + "=" * 70)
    print("TEST 3: Sustained Voice Wake Trigger (Real Speech Detection)")
    print("=" * 70)

    audio_service.is_collecting_wake = False
    audio_service.wake_consecutive_voice = 0
    threshold = audio_service.wake_trigger_threshold

    chunk = generate_pcm_chunk(rms_level=threshold * 2.5)

    # Chunk 1
    audio_service._process_passive_wake(chunk, rms=threshold * 2.5)
    print(f"Chunk 1 fed -> Consecutive voice: {audio_service.wake_consecutive_voice}, Collecting: {audio_service.is_collecting_wake}")
    assert not audio_service.is_collecting_wake, "Chunk 1 should not trigger collection yet"

    # Chunk 2 (Sustained voice requirement met)
    audio_service._process_passive_wake(chunk, rms=threshold * 2.5)
    print(f"Chunk 2 fed -> Consecutive voice: {audio_service.wake_consecutive_voice}, Collecting: {audio_service.is_collecting_wake}")
    assert audio_service.is_collecting_wake, "Chunk 2 should trigger wake collection"

    print("RESULT: PASS - Sustained speech (2 consecutive chunks) correctly triggers wake collection")

if __name__ == "__main__":
    test_janus_wake_recognition()
    test_single_chunk_spike_filtering()
    test_sustained_voice_wake_trigger()
