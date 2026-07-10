import inspect
from kokoro_onnx.tokenizer import Tokenizer
print(inspect.getsource(Tokenizer.phonemize))
