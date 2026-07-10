import os
import sys

# Ensure d:\JARVIS M7 is in system path
sys.path.append(r"d:\JARVIS M7")

from services.tts.kokoro_provider import KokoroProvider

def main():
    print("Initializing KokoroProvider...")
    provider = KokoroProvider()
    
    # Extract voices directly from voices-v1.0.bin
    import numpy as np
    voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"
    voices_data = np.load(voices_path)
    voices = sorted(list(voices_data.files))
    
    out_dir = r"d:\JARVIS M7\scratch\voice_samples_full"
    os.makedirs(out_dir, exist_ok=True)
    
    phrase = "Systems online, Sir."
    print(f"Generating samples for {len(voices)} voices in {out_dir}...")
    
    prefix_map = {
        "af_": "American Female",
        "am_": "American Male",
        "bf_": "British Female",
        "bm_": "British Male",
        "ef_": "Spanish Female",
        "em_": "Spanish Male",
        "ff_": "French Female",
        "hf_": "Hindi Female",
        "hm_": "Hindi Male",
        "if_": "Italian Female",
        "im_": "Italian Male",
        "jf_": "Japanese Female",
        "jm_": "Japanese Male",
        "pf_": "Portuguese Female",
        "pm_": "Portuguese Male",
        "zf_": "Chinese Female",
        "zm_": "Chinese Male",
    }
    
    for i, voice in enumerate(voices, 1):
        # Determine category
        category = "Unknown"
        for pref, cat in prefix_map.items():
            if voice.startswith(pref):
                category = cat
                break
        
        file_path = os.path.join(out_dir, f"{voice}.wav")
        print(f"[{i}/{len(voices)}] Generating {voice} ({category}) -> {file_path}")
        
        try:
            result = provider.synthesize(phrase, voice_id=voice)
            with open(file_path, "wb") as f:
                f.write(result.audio)
        except Exception as e:
            print(f"Error generating sample for {voice}: {e}")
            
    print("All samples generated successfully!")

if __name__ == "__main__":
    main()
