import kokoro_onnx
import soundfile as sf
import os

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

try:
    samples, sample_rate = kokoro.create("Systems online, Sir.", voice="zf_xiaobei", speed=1.0, lang="cmn")
    out_dir = r"d:\JARVIS M7\scratch\voice_samples_full"
    os.makedirs(out_dir, exist_ok=True)
    sf.write(os.path.join(out_dir, "test_zf_xiaobei.wav"), samples, sample_rate)
    print("Synthesis successful!")
except Exception as e:
    print("Synthesis failed:", e)
