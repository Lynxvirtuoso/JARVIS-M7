import sys
import os
import io
import requests

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from services.tts.provider_manager import tts_manager
from services.stt.provider_manager import stt_manager

def main():
    # Make sure stt_provider is set to groq_stt
    config.set("stt_provider", "groq_stt")
    
    test_phrase = "who won the Ballon d'Or in 2024?"
    print(f"Synthesizing test phrase: '{test_phrase}' using local TTS provider: {tts_manager.get_selected_provider().provider_id}...")
    
    try:
        tts_res = tts_manager.synthesize(test_phrase)
        print(f"TTS synthesis successful. Format: {tts_res.format}, Size: {len(tts_res.audio)} bytes.")
    except Exception as e:
        print(f"TTS synthesis failed: {e}")
        # Use a fallback mock audio or exit
        return

    # 1. Run Online Test
    print(f"\n--- Testing STT Priority (Online) ---")
    fallback_order = stt_manager.get_fallback_order()
    print("STT Fallback Order:", fallback_order)
    
    try:
        res = stt_manager.transcribe(tts_res.audio, audio_format=tts_res.format)
        print("\n=== ONLINE TEST SUCCESS ===")
        print(f"  Provider used: {res.provider}")
        print(f"  Transcribed text: '{res.text}'")
    except Exception as e:
        print(f"\n=== ONLINE TEST FAILURE ===")
        print(f"Transcription failed: {e}")

    # 2. Run Offline Test (Fallback)
    print(f"\n--- Testing STT Priority (Offline Fallback) ---")
    
    # Save original post
    original_post = requests.post
    
    # Mock network failure
    def mock_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Simulated offline connection failure")
    requests.post = mock_post
    
    try:
        res = stt_manager.transcribe(tts_res.audio, audio_format=tts_res.format)
        print("\n=== OFFLINE TEST SUCCESS ===")
        print(f"  Provider used: {res.provider}")
        print(f"  Transcribed text: '{res.text}'")
    except Exception as e:
        print(f"\n=== OFFLINE TEST FAILURE ===")
        print(f"Transcription failed: {e}")
        
    # Restore original requests.post
    requests.post = original_post

if __name__ == "__main__":
    main()
