import os
import requests
import json
from core.config import config
from core.logger import logger
from services.brain.base import BrainProvider, BrainResult

def _load_api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return (os.getenv("GROQ_API_KEY") or config.get("groq_api_key", "")).strip()

class GroqBrainProvider(BrainProvider):
    provider_id = "groq"

    def __init__(self):
        self.check_configuration()

    def check_configuration(self):
        api_key = _load_api_key()
        if api_key:
            logger.info("Groq Brain client successfully configured.")
        else:
            logger.warn("Groq API key not found. AI Brain will run in offline fallback mode.")

    def health(self) -> tuple[bool, str]:
        api_key = _load_api_key()
        if not api_key:
            return False, "Groq API Key missing"
        from services.groq_quota_manager import groq_quota_manager
        model_name = config.get("groq_brain_model", "llama-3.3-70b-versatile")
        if not groq_quota_manager.is_available(model_name, "brain"):
            remaining = groq_quota_manager.get_remaining_seconds(model_name, "brain")
            return False, f"Groq is cooling down ({remaining}s remaining)"
        return True, "Ready"

    def think(self, text: str, history: list[dict] = None, search_context: str = None, use_web: bool = False) -> BrainResult:
        if use_web:
            try:
                tokens = list(self.think_compound_mini(text, history))
                res_text = "".join(tokens).strip()
                if res_text:
                    return BrainResult(text=res_text, provider=self.provider_id, success=True)
            except Exception as e:
                logger.warning(f"Groq search-capable path failed: {e}. Falling back to standard model.")

        salutation = config.salutation
        api_key = _load_api_key()
        
        if not api_key:
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error="Groq API key is missing",
                error_type="missing_api_key"
            )

        model_name = config.get("groq_brain_model", "llama-3.3-70b-versatile")
        from services.groq_quota_manager import groq_quota_manager
        if not groq_quota_manager.is_available(model_name, "brain"):
            remaining = groq_quota_manager.get_remaining_seconds(model_name, "brain")
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=f"Groq is cooling down ({remaining}s remaining)",
                error_type="cooldown"
            )

        sys_instruction = (
            f"You are JARVIS M7, a futuristic Windows-first AI operating system inspired by Tony Stark's assistant. "
            f"You MUST address the user as '{salutation}' in every response. "
            f"Keep your responses concise, intellectual, and slightly robotic yet premium. "
            f"If the user asks you to perform an action, describe what you did or are about to do."
        )

        from services.brain.base import format_user_facts_for_prompt, get_uncertainty_guardrail
        sys_instruction += format_user_facts_for_prompt()
        sys_instruction += get_uncertainty_guardrail()

        if search_context:
            sys_instruction += f"\n\nHere is real-time search context retrieved for the query:\n{search_context}\nUse this information to answer accurately. If the search results do not contain the answer or are ambiguous, declare your uncertainty."

        messages = [{"role": "system", "content": sys_instruction}]

        if history:
            for h in history:
                role = "user" if h["role"] == "user" else "assistant"
                messages.append({"role": role, "content": h["content"]})

        messages.append({"role": "user", "content": text})

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7
        }

        try:
            logger.info(f"Thinking via Brain provider: {self.provider_id} (model={model_name})")
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            
            if response.status_code != 200:
                error_text = response.text
                if response.status_code == 429:
                    from services.groq_quota_manager import extract_retry_delay_seconds
                    retry_seconds = extract_retry_delay_seconds(response.headers, error_text)
                    groq_quota_manager.set_cooldown(model_name, retry_seconds, "brain")
                    return BrainResult(
                        text="",
                        provider=self.provider_id,
                        success=False,
                        error="Groq quota is temporarily exhausted",
                        error_type="quota_exceeded"
                    )
                raise RuntimeError(f"Groq Chat API error {response.status_code}: {error_text}")

            res_data = response.json()
            reply = res_data["choices"][0]["message"]["content"].strip()
            return BrainResult(text=reply, provider=self.provider_id, success=True)

        except Exception as e:
            logger.error(f"Groq Brain execution error: {e}", exc_info=True)
            return BrainResult(
                text="",
                provider=self.provider_id,
                success=False,
                error=str(e),
                error_type="execution_error"
            )

    def think_stream(self, text: str, history: list[dict] = None, search_context: str = None, use_web: bool = False):
        if use_web:
            try:
                yield from self.think_compound_mini(text, history)
                return
            except Exception as e:
                logger.warning(f"Groq search-capable streaming path failed: {e}. Falling back to standard model.")

        salutation = config.salutation
        api_key = _load_api_key()
        if not api_key:
            yield f"I am currently offline as the Groq API key is missing. Please configure it in settings, {salutation}."
            return

        model_name = config.get("groq_brain_model", "llama-3.3-70b-versatile")
        from services.groq_quota_manager import groq_quota_manager
        if not groq_quota_manager.is_available(model_name, "brain"):
            remaining = groq_quota_manager.get_remaining_seconds(model_name, "brain")
            yield f"Groq is cooling down, Sir. Please try again in a moment ({remaining}s remaining)."
            return

        sys_instruction = (
            f"You are JARVIS M7, a futuristic Windows-first AI operating system inspired by Tony Stark's assistant. "
            f"You MUST address the user as '{salutation}' in every response. "
            f"Keep your responses concise, intellectual, and slightly robotic yet premium. "
            f"If the user asks you to perform an action, describe what you did or are about to do."
        )

        from services.brain.base import format_user_facts_for_prompt, get_uncertainty_guardrail
        sys_instruction += format_user_facts_for_prompt()
        sys_instruction += get_uncertainty_guardrail()

        if search_context:
            sys_instruction += f"\n\nHere is real-time search context retrieved for the query:\n{search_context}\nUse this information to answer accurately. If the search results do not contain the answer or are ambiguous, declare your uncertainty."

        messages = [{"role": "system", "content": sys_instruction}]

        if history:
            for h in history:
                role = "user" if h["role"] == "user" else "assistant"
                messages.append({"role": role, "content": h["content"]})

        messages.append({"role": "user", "content": text})

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }

        try:
            logger.info(f"Thinking (stream) via Brain provider: {self.provider_id} (model={model_name})")
            response = requests.post(url, headers=headers, json=payload, timeout=20, stream=True)
            
            if response.status_code != 200:
                error_text = response.text
                if response.status_code == 429:
                    from services.groq_quota_manager import extract_retry_delay_seconds
                    retry_seconds = extract_retry_delay_seconds(response.headers, error_text)
                    groq_quota_manager.set_cooldown(model_name, retry_seconds, "brain")
                    yield "Groq quota is temporarily exhausted, Sir. I will use offline controls until it resets."
                    return
                raise RuntimeError(f"Groq Chat API error {response.status_code}: {error_text}")

            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8').strip()
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Groq Brain streaming execution error: {e}", exc_info=True)
            yield f"I encountered a communication issue, {salutation}. The details are logged in the console."

    def think_compound_mini(self, text: str, history: list[dict] = None):
        """
        Calls groq/compound-mini model. Logs search results/citations in executed_tools.
        """
        import time
        salutation = config.salutation
        api_key = _load_api_key()
        if not api_key:
            yield f"I am currently offline as the Groq API key is missing. Please configure it in settings, {salutation}."
            return

        sys_instruction = (
            f"You are JARVIS M7, a futuristic Windows-first AI operating system inspired by Tony Stark's assistant. "
            f"You MUST address the user as '{salutation}' in every response. "
            f"Keep your responses concise, intellectual, and slightly robotic yet premium. "
            f"If the user asks you to perform an action, describe what you did or are about to do."
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

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "groq/compound-mini",
            "messages": messages,
            "temperature": 0.7
        }

        logger.info(f"Thinking (compound-mini) via Brain provider: {self.provider_id}")
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code != 200:
            raise RuntimeError(f"Groq Compound-Mini API error {response.status_code}: {response.text}")

        res_data = response.json()
        message = res_data["choices"][0]["message"]
        reply = message["content"].strip()

        executed_tools = message.get("executed_tools")
        if executed_tools:
            logger.info(f"[Compound-Mini] Executed tools: {json.dumps(executed_tools, indent=2)}")
        else:
            logger.info("[Compound-Mini] No tools were executed.")

        # Yield reply in small chunks to simulate streaming for existing TTS pipeline
        chunk_size = 12
        for i in range(0, len(reply), chunk_size):
            yield reply[i:i+chunk_size]
            time.sleep(0.01)

