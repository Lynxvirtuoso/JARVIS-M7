import sys
import os
import io
import sounddevice as sd
import soundfile as sf
import numpy as np
import requests

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from services.stt.provider_manager import stt_manager

def test_stt(online=True):
    print(f"\n--- Testing STT Priority (Online={online}) ---")
    fallback_order = stt_manager.get_fallback_order()
    print("STT Fallback Order:", fallback_order)
    
    # Save original post
    original_post = requests.post
    
    if not online:
        print("Mocking network/Groq connection failure to simulate offline fallback.")
        def mock_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Simulated offline connection failure")
        requests.post = mock_post
        
    duration = 5.0
    fs = 16000
    print(f"Recording {duration}s. Speak a command now (e.g. proper nouns like Ballon d'Or or specific names)...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()
    print("Recording finished. Transcribing...")
    
    audio_data = recording.flatten()
    wav_io = io.BytesIO()
    sf.write(wav_io, audio_data, fs, format='WAV', subtype='PCM_16')
    wav_bytes = wav_io.getvalue()
    
    try:
        res = stt_manager.transcribe(wav_bytes)
        print("\n=== SUCCESS ===")
        print(f"  Provider used: {res.provider}")
        print(f"  Transcribed text: '{res.text}'")
    except Exception as e:
        print(f"\n=== FAILURE ===")
        print(f"Transcription failed: {e}")
        
    # Restore original requests.post
    requests.post = original_post

if __name__ == "__main__":
    # Update the setting to groq_stt
    config.set("stt_provider", "groq_stt")
    print("Current selected provider:", stt_manager.get_selected_provider().provider_id)
    print("Fallback order:", stt_manager.get_fallback_order())
    
    # Run online test (Groq-primary)
    test_stt(online=True)
    
    # Run offline test (Local fallback)
    test_stt(online=False)
