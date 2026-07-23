import os
import json
import time
import urllib.request
import urllib.error
from enum import Enum
from dataclasses import dataclass
from core.config import config
from core.logger import logger
from services.brain.base import BrainProvider, BrainResult


class OllamaAvailabilityStatus(Enum):
    AVAILABLE = "available"
    SERVICE_UNREACHABLE = "service_unreachable"
    MODEL_NOT_INSTALLED = "model_not_installed"
    INVALID_RESPONSE = "invalid_response"


@dataclass
class ProviderHealth:
    consecutive_service_failures: int = 0
    unavailable_until: float = 0.0
    last_error_type: str | None = None


# Module-level deduplication tracker for missing-model notifications
_NOTIFIED_MISSING_MODELS: set[str] = set()


class OllamaBrainProvider(BrainProvider):
    provider_id = "ollama"

    def __init__(self):
        self.host = config.get("ollama_host", "http://localhost:11434")
        self.health_state = ProviderHealth()

    @property
    def model(self) -> str:
        return config.get("ollama_model", "qwen3:1.7b")

    def _get_validated_context_size(self) -> int:
        val = config.get("ollama_num_ctx", 2048)
        try:
            val_int = int(val)
            if val_int in (2048, 4096):
                return val_int
        except (ValueError, TypeError):
            pass
        return 2048

    def _build_payload(
        self,
        messages: list[dict],
        *,
        stream: bool,
        think: bool | None = None,
    ) -> dict:
        from core.config import parse_bool
        configured_think = parse_bool(config.get("ollama_think", False))

        resolved_think = (
            think
            if think is not None
            else configured_think
        )

        return {
            "model": self.model,
            "messages": messages,
            "think": bool(resolved_think),
            "stream": stream,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.5,
                "num_predict": 150,
                "num_ctx": self._get_validated_context_size(),
            },
        }

    def check_service_health(self, timeout: float = 0.5) -> tuple[bool, str]:
        """Lightweight 500ms check for service reachability."""
        url = f"{self.host.rstrip('/')}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return True, "Service available"
                return False, f"Ollama returned HTTP status {response.status}"
        except urllib.error.URLError as e:
            return False, f"Ollama service unreachable: {e.reason}"
        except Exception as e:
            return False, f"Ollama service check error: {e}"

    def check_availability(self) -> tuple[OllamaAvailabilityStatus, str, list[str]]:
        """Checks service reachability and model existence separately."""
        url = f"{self.host.rstrip('/')}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    models = [m["name"] for m in data.get("models", [])]
                    current_model = self.model.strip()

                    def norm(m_name: str) -> str:
                        return m_name.lower().replace(":latest", "").strip()

                    target_norm = norm(current_model)
                    model_exists = any(
                        target_norm == norm(m) or current_model == m or (m.startswith(current_model) and not m.split(":")[0] != current_model.split(":")[0])
                        for m in models
                    )

                    if not model_exists:
                        for m in models:
                            base_m = m.split(":")[0]
                            base_target = current_model.split(":")[0]
                            tag_m = m.split(":")[1] if ":" in m else ""
                            tag_target = current_model.split(":")[1] if ":" in current_model else ""
                            if base_m == base_target and (tag_m == tag_target or tag_m == f"{tag_target}-latest"):
                                model_exists = True
                                break

                    if model_exists:
                        # Clear missing state if present
                        _NOTIFIED_MISSING_MODELS.discard(current_model)
                        return OllamaAvailabilityStatus.AVAILABLE, f"Ready ({current_model})", models
                    else:
                        return OllamaAvailabilityStatus.MODEL_NOT_INSTALLED, f"Model '{current_model}' not installed.", models
                return OllamaAvailabilityStatus.INVALID_RESPONSE, f"HTTP {response.status}", []
        except urllib.error.URLError as e:
            return OllamaAvailabilityStatus.SERVICE_UNREACHABLE, f"Ollama unreachable: {e.reason}", []
        except Exception as e:
            return OllamaAvailabilityStatus.SERVICE_UNREACHABLE, f"Ollama health check error: {e}", []

    def refresh_models(self) -> tuple[OllamaAvailabilityStatus, str, list[str]]:
        """Queries Ollama again and clears stale missing model notification state."""
        _NOTIFIED_MISSING_MODELS.clear()
        return self.check_availability()

    def health(self) -> tuple[bool, str]:
        now = time.time()
        if self.health_state.unavailable_until > now:
            rem = int(self.health_state.unavailable_until - now)
            return False, f"Ollama in circuit-breaker cooldown ({rem}s remaining)"

        status, msg, models = self.check_availability()
        if status == OllamaAvailabilityStatus.AVAILABLE:
            return True, msg
        elif status == OllamaAvailabilityStatus.MODEL_NOT_INSTALLED:
            return False, f"Model '{self.model}' not installed in Ollama. Pull with: ollama pull {self.model}"
        else:
            return False, msg

    def record_service_failure(self, error_type: str = "service_failure"):
        self.health_state.consecutive_service_failures += 1
        self.health_state.last_error_type = error_type
        if self.health_state.consecutive_service_failures >= 3:
            self.health_state.unavailable_until = time.time() + 60.0
            logger.warning(
                f"Ollama circuit breaker OPENed after 3 consecutive failures. Skipping Ollama for 60s."
            )

    def record_service_success(self):
        self.health_state.consecutive_service_failures = 0
        self.health_state.unavailable_until = 0.0
        self.health_state.last_error_type = None

    def _prepare_messages(self, text: str, history: list[dict] = None) -> list[dict]:
        salutation = config.salutation
        sys_instruction = (
            f"You are JARVIS M7, Tony Stark's futuristic Windows AI. Always address the user as '{salutation}'. "
            f"Keep responses brief, smart, and premium. Describe performed actions clearly."
        )
        from services.brain.base import format_user_facts_for_prompt, get_uncertainty_guardrail
        sys_instruction += format_user_facts_for_prompt()
        sys_instruction += get_uncertainty_guardrail()

        messages = [{"role": "system", "content": sys_instruction}]
        if history:
            for h in history:
                role = "user" if h.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": h.get("content", "")})

        messages.append({"role": "user", "content": text})
        return messages

    def think(self, text: str, history: list[dict] = None, think_override: bool | None = None) -> BrainResult:
        salutation = config.salutation
        url = f"{self.host.rstrip('/')}/api/chat"

        now = time.time()
        if self.health_state.unavailable_until > now:
            rem = int(self.health_state.unavailable_until - now)
            logger.info(f"Ollama skipped: circuit breaker open ({rem}s remaining)")
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=f"Circuit breaker open ({rem}s remaining)",
                error_type="circuit_breaker_open"
            )

        status, status_msg, _ = self.check_availability()
        if status == OllamaAvailabilityStatus.SERVICE_UNREACHABLE:
            self.record_service_failure("service_unreachable")
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=status_msg,
                error_type="service_unreachable"
            )
        elif status == OllamaAvailabilityStatus.MODEL_NOT_INSTALLED:
            current_m = self.model
            if current_m not in _NOTIFIED_MISSING_MODELS:
                _NOTIFIED_MISSING_MODELS.add(current_m)
                msg = f"Selected Ollama model '{current_m}' is missing. Install with: ollama pull {current_m}"
                logger.warning(msg)
                try:
                    from core.event_bus import bus
                    bus.console_log.emit("WARN", msg)
                except Exception:
                    pass
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=f"Model '{current_m}' not installed in Ollama. Pull with: ollama pull {current_m}",
                error_type="model_not_installed"
            )
        elif status == OllamaAvailabilityStatus.INVALID_RESPONSE:
            self.record_service_failure("invalid_response")
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=status_msg,
                error_type="invalid_response"
            )

        messages = self._prepare_messages(text, history)
        payload = self._build_payload(messages, stream=False, think=think_override)

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    msg_obj = data.get("message", {})
                    content = msg_obj.get("content", "").strip()
                    thinking_content = msg_obj.get("thinking", "").strip()

                    self.record_service_success()
                    if content:
                        return BrainResult(
                            text=content,
                            provider=self.provider_id,
                            success=True,
                            thinking=thinking_content
                        )
                    else:
                        return BrainResult(
                            text="",
                            provider=self.provider_id,
                            success=False,
                            error="Empty response content from Ollama",
                            error_type="empty_response",
                            thinking=thinking_content
                        )
                else:
                    self.record_service_failure(f"http_{response.status}")
                    return BrainResult(
                        text="",
                        provider=self.provider_id,
                        success=False,
                        error=f"Ollama returned HTTP status {response.status}",
                        error_type=f"http_{response.status}"
                    )
        except Exception as e:
            logger.error(f"Ollama execution error: {e}", exc_info=True)
            self.record_service_failure("execution_error")
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=str(e),
                error_type="execution_error"
            )

    def think_stream(self, text: str, history: list[dict] = None, think_override: bool | None = None):
        salutation = config.salutation
        url = f"{self.host.rstrip('/')}/api/chat"

        now = time.time()
        if self.health_state.unavailable_until > now:
            logger.info("Ollama stream skipped: circuit breaker open")
            return

        status, status_msg, _ = self.check_availability()
        if status == OllamaAvailabilityStatus.SERVICE_UNREACHABLE:
            self.record_service_failure("service_unreachable")
            return
        elif status == OllamaAvailabilityStatus.MODEL_NOT_INSTALLED:
            current_m = self.model
            if current_m not in _NOTIFIED_MISSING_MODELS:
                _NOTIFIED_MISSING_MODELS.add(current_m)
                logger.warning(
                    f"Selected Ollama model '{current_m}' is missing. Install with: ollama pull {current_m}"
                )
            return

        messages = self._prepare_messages(text, history)
        payload = self._build_payload(messages, stream=True, think=think_override)

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30.0) as response:
                self.record_service_success()
                for line in response:
                    if line:
                        data = json.loads(line.decode('utf-8'))
                        msg_obj = data.get("message", {})
                        content = msg_obj.get("content", "")
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Ollama streaming execution error: {e}", exc_info=True)
            self.record_service_failure("stream_execution_error")
