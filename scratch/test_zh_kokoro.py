import kokoro_onnx

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

for lang in ["zh", "cmn", "zh-cmn", "zh-cn"]:
    try:
        ph = kokoro.tokenizer.phonemize("Systems online, Sir.", lang)
        print(f"kokoro: {lang} supported! Phonemes: {repr(ph)}")
    except Exception as e:
        print(f"kokoro: {lang} failed: {e}")
