import phonemizer

for lang in ["zh", "cmn", "zh-cmn", "zh-cn"]:
    try:
        ph = phonemizer.phonemize("Systems online, Sir.", lang, preserve_punctuation=True, with_stress=True)
        print(f"{lang} supported! Phonemes: {repr(ph)}")
    except Exception as e:
        print(f"{lang} failed: {e}")
