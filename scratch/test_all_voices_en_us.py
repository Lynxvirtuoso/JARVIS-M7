import kokoro_onnx

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)
voices = kokoro.get_voices()

failed = []
for voice in voices:
    try:
        samples, sample_rate = kokoro.create("Systems online, Sir.", voice=voice, lang="en-us")
    except Exception as e:
        failed.append((voice, str(e)))

print("Failed voices:", failed)
print("Total voices:", len(voices))
print("Succeeded voices:", len(voices) - len(failed))
