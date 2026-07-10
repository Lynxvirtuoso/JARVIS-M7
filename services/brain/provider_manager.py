import time
import re
from core.config import config
from core.logger import logger
from services.brain.base import BrainResult
from services.brain.ollama_brain_provider import OllamaBrainProvider
from services.brain.gemini_brain_provider import GeminiBrainProvider
from services.brain.groq_brain_provider import GroqBrainProvider

# Default provider order: cloud Groq first, local Ollama as fallback
_DEFAULT_BRAIN_ORDER = ["groq", "ollama"]

class BrainProviderManager:
    def __init__(self):
        self.providers = {}
        self.register_providers()
        self.health_cache = {}
        self.last_health_check_time = 0.0
        self.health_cache_ttl = 15.0  # 15 seconds cache

    def register_providers(self):
        self.providers["ollama"] = OllamaBrainProvider()
        self.providers["gemini"] = GeminiBrainProvider()
        self.providers["groq"] = GroqBrainProvider()

    def get_selected_provider(self):
        selected = config.get("brain_provider", "groq")
        if selected not in self.providers:
            selected = "groq"
        return self.providers[selected]

    def get_fallback_order(self) -> list[str]:
        selected = config.get("brain_provider", "groq")
        order: list[str] = [selected] if selected in self.providers else ["groq"]
        
        for p in _DEFAULT_BRAIN_ORDER:
            if p in self.providers and p not in order:
                order.append(p)
        return order

    def think(self, text: str, history: list[dict] = None) -> BrainResult:
        fallback_order = ["ollama", "groq", "gemini"]

        last_error = None
        health_report = self.get_health_report()

        for i, provider_id in enumerate(fallback_order):
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            status_info = health_report.get(provider_id, {"healthy": False, "status": "Unknown"})
            if not status_info["healthy"]:
                if i == 0:
                    logger.warning(
                        f"Brain provider {provider_id!r} is unhealthy: {status_info['status']}. Skipping."
                    )
                continue

            try:
                logger.info(f"Thinking via Brain provider: {provider_id}")
                return provider.think(text, history)
            except Exception as e:
                logger.error(f"Brain provider {provider_id!r} failed: {e}")
                last_error = e
                next_idx = i + 1
                if next_idx < len(fallback_order):
                    next_p = fallback_order[next_idx]
                    logger.warning(f"Brain provider {provider_id!r} failed. Falling back to {next_p!r}.")

                    try:
                        is_healthy, status = provider.health()
                        self.health_cache[provider_id] = {"healthy": is_healthy, "status": status}
                    except Exception:
                        self.health_cache[provider_id] = {"healthy": False, "status": "Error"}

        raise RuntimeError("All Brain providers failed.") from last_error

    def think_stream(self, text: str, history: list[dict] = None):
        fallback_order = ["ollama", "groq", "gemini"]

        last_error = None
        health_report = self.get_health_report()

        for i, provider_id in enumerate(fallback_order):
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            status_info = health_report.get(provider_id, {"healthy": False, "status": "Unknown"})
            if not status_info["healthy"]:
                continue

            try:
                logger.info(f"Thinking (stream) via Brain provider: {provider_id}")
                if hasattr(provider, "think_stream"):
                    yield from provider.think_stream(text, history)
                else:
                    res = provider.think(text, history)
                    yield res.text
                return
            except Exception as e:
                logger.error(f"Brain provider {provider_id!r} stream failed: {e}")
                last_error = e

        yield f"All Brain providers failed. Last error: {last_error}"

    def get_health_report(self, force: bool = False) -> dict:
        now = time.time()
        if force or not self.health_cache or (now - self.last_health_check_time) > self.health_cache_ttl:
            report = {}
            for pid, provider in self.providers.items():
                try:
                    is_healthy, status = provider.health()
                except Exception as e:
                    is_healthy, status = False, f"Error: {e}"
                report[pid] = {"healthy": is_healthy, "status": status}
            self.health_cache = report
            self.last_health_check_time = now
        return self.health_cache

brain_manager = BrainProviderManager()
