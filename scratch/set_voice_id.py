import sys
sys.path.append(r"d:\JARVIS M7")
from core.config import config

print("Old voice in DB/JSON:", config.get("tts_voice_id"))
config.set("tts_voice_id", "am_michael")
print("New voice in DB/JSON:", config.get("tts_voice_id"))
