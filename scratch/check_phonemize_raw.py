import kokoro_onnx
import phonemizer

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

for lang in ["en-us", "en-gb", "es", "fr-fr", "hi", "it", "ja", "pt-br", "zh"]:
    try:
        raw_ph = phonemizer.phonemize("Systems online, Sir.", lang, preserve_punctuation=True, with_stress=True)
        print(f"lang {lang} -> Raw: {repr(raw_ph)}")
        # Check how many of these characters are in vocab
        in_vocab = "".join([c for c in raw_ph if c in kokoro.tokenizer.vocab])
        print(f"lang {lang} -> In Vocab: {repr(in_vocab)}")
    except Exception as e:
        print(f"lang {lang} -> ERROR: {e}")
