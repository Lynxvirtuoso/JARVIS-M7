import time
import re
from core.logger import logger

from core.database import db

class ProviderUnavailable(RuntimeError):
    pass

class GroqQuotaManager:
    def __init__(self):
        self.cooldowns = {}
        self.load_cooldowns()

    def load_cooldowns(self):
        try:
            persisted = db.get_cooldowns()
            now = time.time()
            for key, until in persisted.items():
                if key.startswith("groq:") and until > now:
                    parts = key.split(":", 2)
                    if len(parts) == 3:
                        internal_key = f"{parts[1]}:{parts[2]}"
                        self.cooldowns[internal_key] = until
                        logger.info(f"Restored Groq cooldown for {internal_key} until {until}")
                elif key.startswith("groq:") and until <= now:
                    db.remove_cooldown(key)
        except Exception as e:
            logger.error(f"Error loading Groq cooldowns: {e}")

    def is_available(self, model: str, service: str = "global") -> bool:
        key = f"{service}:{model}"
        until = self.cooldowns.get(key)
        if until and time.time() >= until:
            if key in self.cooldowns:
                del self.cooldowns[key]
            db_key = f"groq:{key}"
            db.remove_cooldown(db_key)
            return True
        return not until

    def set_cooldown(self, model: str, retry_seconds: int, service: str = "global"):
        key = f"{service}:{model}"
        until = time.time() + max(retry_seconds, 5)
        self.cooldowns[key] = until
        db_key = f"groq:{key}"
        db.set_cooldown(db_key, until)

    def get_remaining_seconds(self, model: str, service: str = "global") -> int:
        key = f"{service}:{model}"
        until = self.cooldowns.get(key, 0)
        return max(0, int(until - time.time()))

def extract_retry_delay_seconds(headers: dict, response_body: str = "") -> int:
    if headers:
        for k in ["retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"]:
            val = headers.get(k) or headers.get(k.lower())
            if val:
                try:
                    clean_val = str(val).rstrip('s')
                    return int(float(clean_val))
                except ValueError:
                    pass
    if response_body:
        match = re.search(r'(?:try\s+again\s+in|retry\s+in|after)\s+(\d+(?:\.\d+)?)\s*s?', response_body, re.IGNORECASE)
        if match:
            try:
                return int(float(match.group(1)))
            except ValueError:
                pass
    return 60

groq_quota_manager = GroqQuotaManager()
