import sys
sys.path.append(r"d:\JARVIS M7")

from services.tts.kokoro_provider import KokoroProvider
from core.config import config

print("Configured default voice:", config.get("tts_voice_id"))

provider = KokoroProvider()
result = provider.synthesize("Systems online, Sir.")
print("Synthesized audio with default voice, size:", len(result.audio))
print("Synthesized voice ID:", result.voice_id)
