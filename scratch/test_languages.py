import kokoro_onnx

model_path = r"d:\JARVIS M7\models\kokoro-v1.0.onnx"
voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"

kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

prefixes_and_langs = [
    ("af_", "en-us"),
    ("am_", "en-us"),
    ("bf_", "en-gb"),
    ("bm_", "en-gb"),
    ("ef_", "es"),
    ("em_", "es"),
    ("ff_", "fr-fr"),
    ("hf_", "hi"),
    ("hm_", "hi"),
    ("if_", "it"),
    ("im_", "it"),
    ("jf_", "ja"),
    ("jm_", "ja"),
    ("pf_", "pt-br"),
    ("pm_", "pt-br"),
    ("zf_", "zh"),
    ("zm_", "zh"),
]

for pref, lang in prefixes_and_langs:
    try:
        pho = kokoro.tokenizer.phonemize("Systems online, Sir.", lang)
        print(f"Prefix {pref} with lang {lang} -> Phonemes length: {len(pho)}")
    except Exception as e:
        print(f"ERROR: Prefix {pref} with lang {lang} failed: {e}")
