import os
import json
import urllib.request
import urllib.error
from core.config import config
from core.logger import logger
from services.brain.base import BrainProvider, BrainResult

class OllamaBrainProvider(BrainProvider):
    provider_id = "ollama"

    def __init__(self):
        self.host = config.get("ollama_host", "http://localhost:11434")
        self.model = config.get("ollama_model", "qwen2.5:1.5b")

    def health(self) -> tuple[bool, str]:
        url = f"{self.host.rstrip('/')}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    models = [m["name"] for m in data.get("models", [])]
                    model_exists = any(self.model in m or m in self.model for m in models)
                    if model_exists:
                        return True, f"Ready ({self.model})"
                    else:
                        return False, f"Model '{self.model}' not found in Ollama. Available: {models}"
                return False, f"Ollama returned HTTP status {response.status}"
        except urllib.error.URLError as e:
            return False, f"Ollama unreachable: {e.reason}"
        except Exception as e:
            return False, f"Ollama health check error: {e}"

    def think(self, text: str, history: list[dict] = None) -> BrainResult:
        salutation = config.salutation
        url = f"{self.host.rstrip('/')}/api/chat"

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
                role = "user" if h["role"] == "user" else "assistant"
                messages.append({"role": role, "content": h["content"]})

        messages.append({"role": "user", "content": text})

        payload = {
            "model": self.model,
            "messages": messages,
            "options": {
                "temperature": 0.7,
                "num_predict": 200,
                "num_ctx": 2048
            },
            "stream": False,
            "keep_alive": "30m"
        }

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
                    reply = data.get("message", {}).get("content", "").strip()
                    return BrainResult(text=reply, provider=self.provider_id)
                return BrainResult(
                    text=f"I encountered a connection error with local Ollama, {salutation}.",
                    provider=self.provider_id
                )
        except Exception as e:
            logger.error(f"Ollama execution error: {e}", exc_info=True)
            return BrainResult(
                text=f"I encountered a communication issue with local Ollama, {salutation}.",
                provider=self.provider_id
            )

    def think_stream(self, text: str, history: list[dict] = None):
        salutation = config.salutation
        url = f"{self.host.rstrip('/')}/api/chat"

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
                role = "user" if h["role"] == "user" else "assistant"
                messages.append({"role": role, "content": h["content"]})

        messages.append({"role": "user", "content": text})

        payload = {
            "model": self.model,
            "messages": messages,
            "options": {
                "temperature": 0.7,
                "num_predict": 200,
                "num_ctx": 2048
            },
            "stream": True,
            "keep_alive": "30m"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30.0) as response:
            for line in response:
                if line:
                    data = json.loads(line.decode('utf-8'))
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
