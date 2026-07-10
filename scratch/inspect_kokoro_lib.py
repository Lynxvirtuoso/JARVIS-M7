import inspect
import kokoro_onnx

print("Kokoro methods:")
print(inspect.signature(kokoro_onnx.Kokoro.create))
print("Available voice/language maps if any:")
for attr in dir(kokoro_onnx.Kokoro):
    if not attr.startswith("_"):
        print(attr)
