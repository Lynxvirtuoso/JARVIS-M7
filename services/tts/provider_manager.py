import time
import threading
from core.config import config
from core.logger import logger
from services.tts.windows_sapi_provider import WindowsSapiProvider
from services.tts.piper_provider import PiperProvider
from services.tts.kokoro_provider import KokoroProvider
from services.tts.openai_tts_provider import OpenAIWhisperTTSProvider
from services.tts.cartesia_provider import CartesiaProvider
from services.tts.gemini_tts_provider import GeminiTTSProvider
from services.tts.base import TTSResult

# Default provider order: Kokoro first, Windows SAPI as emergency fallback
_DEFAULT_TTS_ORDER = ["kokoro", "windows_sapi"]


def _openai_enabled() -> bool:
    return config.get("openai_enabled", "false").lower() == "true"


def is_important_reply(text: str) -> bool:
    # A reply is important if it's long (e.g., informative answer from brain)
    # or contains key information.
    # Short replies (e.g. <= 12 words or <= 60 chars) are NOT important.
    words = text.split()
    if len(words) <= 12 or len(text) <= 60:
        return False
    # If it's a simple confirmation/status, it's not important
    lower_text = text.lower()
    for prefix in ["opening ", "closing ", "yes, ", "sorry ", "command ", "did you mean"]:
        if lower_text.startswith(prefix):
            return False
    return True


class TTSProviderManager:
    def __init__(self):
        self.providers = {}
        self.register_providers()
        self.health_cache = {}
        self.last_health_check_time = 0
        self.health_cache_ttl = 30  # seconds
        self.interrupt_flag = threading.Event()

    def stop_speaking(self) -> None:
        logger.info("TTS interrupt triggered. Stopping all speech playback.")
        self.interrupt_flag.set()
        try:
            from services.tts.streaming_tts_queue import streaming_tts_queue
            streaming_tts_queue.cancel_active_request()
        except Exception as e:
            logger.error(f"Failed to cancel streaming TTS queue: {e}")
        try:
            from services.speech_service import speech
            speech.clear_queue()
        except Exception as e:
            logger.error(f"Failed to clear speech queue: {e}")
        sapi = self.providers.get("windows_sapi")
        if sapi and hasattr(sapi, "stop_speaking"):
            sapi.stop_speaking()

    def clear_interrupt(self) -> None:
        self.interrupt_flag.clear()

    def register_providers(self):
        """Register all TTS providers. OpenAI TTS is registered but excluded from
        the active order unless openai_enabled=true."""
        self.providers["windows_sapi"] = WindowsSapiProvider()
        self.providers["piper"] = PiperProvider()
        self.providers["kokoro"] = KokoroProvider()
        self.providers["openai_tts"] = OpenAIWhisperTTSProvider()
        self.providers["cartesia"] = CartesiaProvider()
        self.providers["gemini_tts"] = GeminiTTSProvider()

    def get_selected_provider(self):
        selected = config.get("tts_provider", "kokoro")
        if selected not in self.providers:
            selected = "kokoro"
        return self.providers[selected]

    def get_fallback_order(self) -> list[str]:
        selected = config.get("tts_provider", "kokoro")

        order: list[str] = [selected] if selected in self.providers else ["kokoro"]

        # Always add gemini_tts and windows_sapi
        for p in _DEFAULT_TTS_ORDER:
            if p in self.providers and p not in order:
                order.append(p)

        # Optionally add others (non-OpenAI) in case user selected them
        for p in ["cartesia", "kokoro", "piper"]:
            if p in self.providers and p not in order:
                order.append(p)

        # Filter out OpenAI providers unless explicitly enabled
        if not _openai_enabled():
            openai_ids = {"openai_tts"}
            removed = [p for p in order if p in openai_ids]
            if removed:
                logger.info(f"OpenAI TTS providers excluded (openai_enabled=false): {removed}")
            order = [p for p in order if p not in openai_ids]

        # windows_sapi is ALWAYS the last resort emergency fallback
        if "windows_sapi" in order and order[-1] != "windows_sapi":
            order.remove("windows_sapi")
            order.append("windows_sapi")
        elif "windows_sapi" not in order:
            order.append("windows_sapi")

        return order

    def speak(self, text: str) -> None:
        fallback_order = self.get_fallback_order()

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
                        f"TTS provider {provider_id!r} is unhealthy: {status_info['status']}. Skipping."
                    )
                continue

            try:
                logger.info(f"Speaking via TTS provider: {provider_id}")
                provider.speak(text)
                return
            except Exception as e:
                logger.error(f"TTS provider {provider_id!r} failed: {e}")
                last_error = e
                next_idx = i + 1
                if next_idx < len(fallback_order):
                    next_p = fallback_order[next_idx]
                    logger.warning(f"TTS {provider_id!r} failed. Falling back to {next_p!r}.")

                    # Force health re-check so permanent failures (Gemini session cache)
                    # are respected immediately on next iteration
                    try:
                        is_healthy, status = provider.health()
                        self.health_cache[provider_id] = {"healthy": is_healthy, "status": status}
                    except Exception:
                        self.health_cache[provider_id] = {"healthy": False, "status": "Error"}

        logger.error("All TTS providers failed.")
        # Absolute last resort fallback output
        logger.info(f"JARVIS (Fallback): {text}")

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
    ) -> TTSResult:
        fallback_order = self.get_fallback_order()

        last_error = None
        health_report = self.get_health_report()

        for provider_id in fallback_order:
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            status_info = health_report.get(provider_id, {"healthy": False, "status": "Unknown"})
            if not status_info["healthy"]:
                continue

            try:
                return provider.synthesize(text, voice_id=voice_id, speed=speed)
            except Exception as e:
                logger.error(f"TTS synthesize provider {provider_id!r} failed: {e}")
                last_error = e

    def play_result(self, result: TTSResult) -> None:
        import io
        import soundfile as sf
        import sounddevice as sd
        
        data, fs = sf.read(io.BytesIO(result.audio), dtype='float32')
        chunk_size = int(fs * 0.15)  # 150ms chunks
        channels = 1 if len(data.shape) == 1 else data.shape[1]
        interrupted = False

        from core.telemetry import pipeline_timer
        pipeline_timer.log_event("TTS audio starts playing")
        with sd.OutputStream(samplerate=fs, channels=channels, dtype='float32') as stream:
            for i in range(0, len(data), chunk_size):
                if self.interrupt_flag.is_set():
                    interrupted = True
                    break
                chunk = data[i:i+chunk_size]
                stream.write(chunk)

        if interrupted:
            logger.info(f"Playback from provider {result.provider!r} halted due to interrupt.")


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


tts_manager = TTSProviderManager()
