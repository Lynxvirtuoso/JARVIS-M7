import time
from core.config import config
from core.logger import logger
from services.stt.local_faster_whisper_provider import LocalFasterWhisperProvider
from services.stt.openai_whisper_provider import OpenAIWhisperProvider
from services.stt.deepgram_provider import DeepgramProvider
from services.stt.gemini_stt_provider import GeminiSTTProvider
from services.stt.openai_stt_provider import OpenAISTTProvider
from services.stt.base import STTResult

from services.stt.groq_stt_provider import GroqSTTProvider

# Default provider order — Groq first, local as fallback
_DEFAULT_STT_ORDER = ["groq_stt", "local_faster_whisper"]


def _openai_enabled() -> bool:
    return config.get("openai_enabled", "false").lower() == "true"


class STTProviderManager:
    def __init__(self):
        self.providers = {}
        self.register_providers()
        self.health_cache = {}
        self.last_health_check_time = 0
        self.health_cache_ttl = 30  # seconds

    def register_providers(self):
        """Register all known providers. OpenAI providers are registered but
        excluded from the active order unless openai_enabled=true."""
        for provider in [
            LocalFasterWhisperProvider(),
            DeepgramProvider(),
            GeminiSTTProvider(),
            OpenAISTTProvider(),
            OpenAIWhisperProvider(),
            GroqSTTProvider(),
        ]:
            self.providers[provider.provider_id] = provider

    def get_selected_provider(self):
        selected = config.get("stt_provider", "groq_stt")
        if selected not in self.providers:
            selected = "groq_stt"
        return self.providers[selected]

    def get_fallback_order(self) -> list[str]:
        stt_mode = config.get("stt_mode", "cloud_first")

        if stt_mode == "offline_only":
            return ["local_faster_whisper"]

        selected = config.get("stt_provider", "groq_stt")

        order: list[str] = [selected] if selected in self.providers else ["groq_stt"]

        # Ensure local_faster_whisper and gemini_stt are always present
        for p in _DEFAULT_STT_ORDER:
            if p in self.providers and p not in order:
                order.append(p)

        # Optionally add others in case user selected them
        for p in ["local_faster_whisper", "groq_stt", "deepgram"]:
            if p in self.providers and p not in order:
                order.append(p)

        # Filter out OpenAI providers unless explicitly enabled
        if not _openai_enabled():
            openai_ids = {"openai_stt", "openai_whisper"}
            removed = [p for p in order if p in openai_ids]
            if removed:
                logger.info(f"OpenAI STT providers excluded (openai_enabled=false): {removed}")
            order = [p for p in order if p not in openai_ids]

        return order

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None,
    ) -> STTResult:
        fallback_order = self.get_fallback_order()
        last_error = None

        health_report = self.get_health_report()

        for i, provider_id in enumerate(fallback_order):
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            if provider_id == "gemini_stt":
                from services.gemini_quota_manager import gemini_quota_manager
                if not gemini_quota_manager.is_available(config.gemini_stt_model, "stt"):
                    logger.info("Skipping Gemini STT during cooldown. Using local_faster_whisper.")
                    continue
                if config.gemini_quota_saver_mode:
                    from services.audio_service import audio_service
                    rms = getattr(audio_service, "last_avg_rms", 1.0)
                    dur = getattr(audio_service, "last_duration", 1.0)
                    MIN_COMMAND_RMS_FOR_CLOUD_STT = 0.018
                    MIN_COMMAND_DURATION_FOR_CLOUD_STT = 0.7
                    if rms < MIN_COMMAND_RMS_FOR_CLOUD_STT or dur < MIN_COMMAND_DURATION_FOR_CLOUD_STT:
                        logger.info("Skip Gemini STT: command audio too quiet. Use local fallback or ignore.")
                        continue

            if provider_id == "groq_stt":
                from services.groq_quota_manager import groq_quota_manager
                stt_model = config.get("groq_stt_model", "whisper-large-v3-turbo")
                if not groq_quota_manager.is_available(stt_model, "stt"):
                    logger.info("Skipping Groq STT during cooldown. Using local fallback.")
                    continue

            status_info = health_report.get(provider_id, {"healthy": False, "status": "Unknown"})
            if not status_info["healthy"]:
                logger.warning(
                    f"STT provider {provider_id!r} is unhealthy: {status_info['status']}. Skipping."
                )
                continue

            try:
                logger.info(f"STT provider selected: {provider_id}")
                result = provider.transcribe(
                    audio_bytes,
                    audio_format=audio_format,
                    language=language,
                    initial_prompt=initial_prompt,
                )
                if result and result.text:
                    return result
                # Empty transcription — try next
                if provider_id == "gemini_stt":
                    logger.info("Gemini STT returned no transcription text. Trying local fallback.")
                else:
                    logger.warning(f"STT provider {provider_id!r} returned empty text. Trying next.")
            except Exception as e:
                # If provider already raised ProviderUnavailable, let's catch and log it cleanly
                logger.error(f"STT provider {provider_id!r} failed: {e}")
                last_error = e
                next_idx = i + 1
                if next_idx < len(fallback_order):
                    logger.warning(
                        f"STT provider {provider_id!r} failed. Falling back to {fallback_order[next_idx]!r}."
                    )

        logger.error("All STT providers failed.")
        raise RuntimeError("All STT providers failed.") from last_error


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


stt_manager = STTProviderManager()
