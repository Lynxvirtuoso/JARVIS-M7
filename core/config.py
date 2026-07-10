import os
import json
from dotenv import load_dotenv
from core.database import db
from core.logger import logger

# Load environment variables from .env if present
load_dotenv()

class ConfigManager:
    """Manages application configurations combined from Environment, SQLite, and config.json."""
    def __init__(self, json_path="config.json"):
        self.json_path = json_path
        self.load_from_json()

    def load_from_json(self):
        self.json_config = {}
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.json_config = json.load(f)
                logger.info(f"Loaded configurations from {self.json_path}")
            except Exception as e:
                logger.error(f"Error reading config.json: {e}")

    def get(self, key, default=None):
        # 1. Try Environment variables (uppercase)
        env_val = os.getenv(key.upper())
        if env_val is not None:
            return env_val
            
        # 2. Try SQLite Database settings
        db_val = db.get_setting(key)
        if db_val is not None:
            return db_val
            
        # 3. Try config.json
        if key in self.json_config:
            return self.json_config[key]
            
        if key == "stt_provider":
            return default or "groq_stt"
        if key == "tts_provider":
            return default or "kokoro"
        return default

    def set(self, key, value):
        # Hook for autostart registry toggle
        if key == "autostart_enabled":
            try:
                from core.autostart import sync_autostart_with_config
                sync_autostart_with_config(value)
            except Exception as e:
                logger.error(f"Registry toggle failed: {e}")
                raise

        # Update database
        db.set_setting(key, value)
        
        # Optionally update config.json if it exists or for certain keys
        self.json_config[key] = value
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.json_config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving to config.json: {e}")

    @property
    def gemini_api_key(self):
        return self.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")

    @property
    def salutation(self):
        return self.get("salutation", "Sir")

    @property
    def home_assistant_url(self):
        return self.get("home_assistant_url")

    @property
    def home_assistant_token(self):
        return self.get("home_assistant_token")

    @property
    def gemini_stt_model(self):
        return self.get("gemini_stt_model", "gemini-2.5-flash")

    @property
    def gemini_tts_model(self):
        return self.get("gemini_tts_model", "gemini-2.5-flash-preview-tts")

    @property
    def gemini_quota_saver_mode(self):
        val = self.get("gemini_quota_saver_mode")
        if val is None:
            return True
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    @property
    def trust_gate_typed_min_confidence(self):
        return float(self.get("trust_gate_typed_min_confidence", 0.4))

    @property
    def trust_gate_voice_min_confidence(self):
        return float(self.get("trust_gate_voice_min_confidence", 0.6))

    @property
    def trust_gate_voice_min_audio_quality(self):
        return float(self.get("trust_gate_voice_min_audio_quality", 0.5))

    @property
    def trust_gate_voice_confirm_confidence(self):
        return float(self.get("trust_gate_voice_confirm_confidence", 0.3))

    @property
    def autostart_enabled(self) -> bool:
        val = self.get("autostart_enabled")
        if val is None:
            return False
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    @property
    def response_popup_dismiss_delay(self) -> int:
        try:
            return int(self.get("response_popup_dismiss_delay", 5))
        except (ValueError, TypeError):
            return 5

# Global configuration instance
config = ConfigManager()


