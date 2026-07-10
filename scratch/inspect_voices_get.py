import kokoro_onnx

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)
print("get_voices():", kokoro.get_voices())
