import time
import re
from enum import Enum
from dataclasses import dataclass
from core.config import config
from core.logger import logger
from services.brain.base import BrainResult
from services.brain.ollama_brain_provider import OllamaBrainProvider
from services.brain.gemini_brain_provider import GeminiBrainProvider
from services.brain.groq_brain_provider import GroqBrainProvider


class BrainRoute(Enum):
    DIRECT_COMMAND = "direct_command"
    SIMPLE_CHAT = "simple_chat"
    PRIVATE_LOCAL = "private_local"
    COMPLEX_REASONING = "complex_reasoning"
    CURRENT_INFORMATION = "current_information"
    MULTIMODAL = "multimodal"


@dataclass
class BrainRequest:
    text: str
    contains_private_data: bool = False
    local_only: bool = False
    cloud_allowed: bool = True
    needs_current_information: bool = False


def get_provider_order(selected: str) -> list[str]:
    fallback_order = ["ollama", "groq", "gemini"]
    if selected not in fallback_order:
        selected = "groq"

    return [selected] + [p for p in fallback_order if p != selected]


def is_valid_result(result: BrainResult) -> bool:
    return (
        result is not None
        and getattr(result, "success", True) is True
        and isinstance(getattr(result, "text", None), str)
        and bool(result.text.strip())
    )


PRIVATE_PHRASES = [
    "keep this local",
    "keep this private",
    "do not send this online",
    "don't send this online",
    "offline only",
    "use the local model",
    "use ollama only",
    "do not use the cloud",
    "don't use the cloud",
    "answer locally",
    "process this locally",
    "private mode",
]


class BrainProviderManager:
    def __init__(self):
        self.providers = {}
        self.register_providers()

    def register_providers(self):
        self.providers["ollama"] = OllamaBrainProvider()
        self.providers["gemini"] = GeminiBrainProvider()
        self.providers["groq"] = GroqBrainProvider()

    def get_selected_provider(self):
        selected = config.get("brain_provider", "groq")
        if selected not in self.providers:
            selected = "groq"
        return self.providers[selected]

    def get_fallback_order(self, selected: str = None) -> list[str]:
        if not selected:
            selected = config.get("brain_provider", "groq")
        return get_provider_order(selected)

    def determine_route(self, request: BrainRequest | str) -> tuple[BrainRoute, list[str], bool]:
        if isinstance(request, str):
            req = BrainRequest(text=request)
        else:
            req = request

        text_lower = req.text.lower().strip()

        from core.config import parse_bool
        # Check private phrases
        is_private_phrase = any(
            re.search(rf"\b{re.escape(phrase)}\b", text_lower)
            for phrase in PRIVATE_PHRASES
        )

        # Local-only override check
        if parse_bool(config.get("local_only_mode", False)) or req.local_only or is_private_phrase or (req.contains_private_data and not req.cloud_allowed):
            return BrainRoute.PRIVATE_LOCAL, ["ollama"], False

        # Brain mode check
        brain_mode = config.get("brain_mode", "smart_auto")
        if brain_mode == "manual":
            selected = config.get("brain_provider", "groq")
            order = get_provider_order(selected)
            from core.brain import needs_web_search
            web_needed = req.needs_current_information or needs_web_search(req.text)
            return BrainRoute.SIMPLE_CHAT, order, web_needed

        # Multimodal request indicator
        if getattr(req, "is_multimodal", False) or "attached image" in text_lower or "image attached" in text_lower or "describe this image" in text_lower:
            return BrainRoute.MULTIMODAL, ["gemini", "groq"], False

        # Smart Auto Mode classification
        from core.brain import needs_web_search
        web_needed = req.needs_current_information or needs_web_search(req.text)

        # Coding / reasoning indicators (word boundaries and traceback/explain detection)
        coding_keywords = ["code", "script", "python", "function", "debug", "algorithm", "refactor", "program", "traceback", "stack trace", "error log"]
        is_complex = any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in coding_keywords) or text_lower.startswith("explain this python") or len(req.text.split()) > 25

        if web_needed:
            return BrainRoute.CURRENT_INFORMATION, ["groq", "gemini", "ollama"], True
        elif is_complex:
            return BrainRoute.COMPLEX_REASONING, ["groq", "gemini", "ollama"], False
        else:
            return BrainRoute.SIMPLE_CHAT, ["ollama", "groq", "gemini"], False

    def think(self, request: BrainRequest | str, history: list[dict] = None) -> BrainResult:
        if isinstance(request, str):
            req = BrainRequest(text=request)
        else:
            req = request

        start_time = time.monotonic()
        route, provider_order, web_needed = self.determine_route(req)

        logger.info(
            f"Brain route: {route.value.upper()} | Brain mode: {config.get('brain_mode', 'smart_auto').upper()} | "
            f"Providers: {provider_order} | Web search: {web_needed}"
        )

        # Web-enabled search handling if route requires it
        if web_needed and "groq" in provider_order:
            groq_provider = self.providers.get("groq")
            if groq_provider and hasattr(groq_provider, "think_compound_mini"):
                try:
                    logger.info("Routing query to Web-enabled Groq compound-mini...")
                    res_tokens = list(groq_provider.think_compound_mini(req.text, history))
                    res_text = "".join(res_tokens).strip()
                    if res_text:
                        latency_ms = int((time.monotonic() - start_time) * 1000)
                        logger.info(f"Brain execution successful (web-groq) | Latency: {latency_ms} ms")
                        return BrainResult(text=res_text, provider="groq", success=True)
                except Exception as e:
                    logger.warning(f"Web-enabled Groq search failed: {e}. Falling back to standard provider order.")

        last_error = None
        for provider_id in provider_order:
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            try:
                if provider_id == "groq":
                    res = provider.think(req.text, history, use_web=web_needed)
                else:
                    res = provider.think(req.text, history)
                if is_valid_result(res):
                    latency_ms = int((time.monotonic() - start_time) * 1000)
                    logger.info(
                        f"Brain route: {route.value.upper()} | Selected provider: {provider_id} | "
                        f"Model: {getattr(provider, 'model', 'default')} | Thinking: disabled | "
                        f"Web search: {web_needed} | Fallback used: {'yes' if provider_id != provider_order[0] else 'no'} | "
                        f"Latency: {latency_ms} ms"
                    )
                    return res
                else:
                    err_msg = getattr(res, "error", "Invalid or empty response")
                    err_type = getattr(res, "error_type", "invalid_response")
                    logger.warning(f"Provider skipped: {provider_id} | Reason: {err_type} ({err_msg})")
            except Exception as e:
                logger.error(f"Brain provider {provider_id!r} failed: {e}")
                last_error = e

        salutation = config.salutation
        return BrainResult(
            text=f"I apologize {salutation}, all available AI brain providers are currently unreachable.",
            provider="none",
            success=False,
            error=str(last_error) if last_error else "All providers failed",
            error_type="all_providers_failed"
        )

    def think_stream(self, request: BrainRequest | str, history: list[dict] = None):
        if isinstance(request, str):
            req = BrainRequest(text=request)
        else:
            req = request

        route, provider_order, web_needed = self.determine_route(req)

        if web_needed and "groq" in provider_order:
            groq_provider = self.providers.get("groq")
            if groq_provider and hasattr(groq_provider, "think_compound_mini"):
                try:
                    yield from groq_provider.think_compound_mini(req.text, history)
                    return
                except Exception as e:
                    logger.warning(f"Web-enabled Groq search stream failed: {e}. Falling back to standard stream.")

        for provider_id in provider_order:
            provider = self.providers.get(provider_id)
            if provider is None:
                continue

            try:
                if hasattr(provider, "think_stream"):
                    chunk_yielded = False
                    for chunk in provider.think_stream(req.text, history):
                        if chunk:
                            chunk_yielded = True
                            yield chunk
                    if chunk_yielded:
                        return
                else:
                    res = provider.think(req.text, history)
                    if is_valid_result(res):
                        yield res.text
                        return
            except Exception as e:
                logger.error(f"Brain provider {provider_id!r} stream failed: {e}")

        salutation = config.salutation
        yield f"All Brain providers failed, {salutation}."

    def get_health_report(self, force: bool = False) -> dict:
        report = {}
        for pid, provider in self.providers.items():
            try:
                is_healthy, status = provider.health()
            except Exception as e:
                is_healthy, status = False, f"Error: {e}"
            report[pid] = {"healthy": is_healthy, "status": status}
        return report


brain_manager = BrainProviderManager()
