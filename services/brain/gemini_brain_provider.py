from google import genai
from google.genai import types
from core.config import config
from core.logger import logger
from services.brain.base import BrainProvider, BrainResult

class GeminiBrainProvider(BrainProvider):
    provider_id = "gemini"

    def __init__(self):
        self.model_name = "gemini-2.5-flash"
        self.client = None
        self.check_configuration()

    def check_configuration(self):
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or config.gemini_api_key
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                logger.info("Gemini GenAI client successfully configured.")
            except Exception as e:
                logger.error(f"Error configuring Gemini client: {e}")
                self.client = None
        else:
            logger.warn("Gemini API key not found. AI Brain will run in offline fallback mode.")
            self.client = None

    def health(self) -> tuple[bool, str]:
        if not self.client:
            self.check_configuration()
        if not self.client:
            return False, "Gemini API Key missing"
        from services.gemini_quota_manager import gemini_quota_manager
        if not gemini_quota_manager.is_available(self.model_name, "brain"):
            remaining = gemini_quota_manager.get_remaining_seconds(self.model_name, "brain")
            return False, f"Gemini is cooling down ({remaining}s remaining)"
        return True, "Ready"

    def think(self, text: str, history: list[dict] = None) -> BrainResult:
        if not self.client:
            self.check_configuration()
            
        salutation = config.salutation
        
        if not self.client:
            return BrainResult(
                text=f"I am currently offline as the Gemini API key is missing. Please configure it in settings, {salutation}.",
                provider=self.provider_id
            )

        from services.gemini_quota_manager import gemini_quota_manager
        if not gemini_quota_manager.is_available(self.model_name, "brain"):
            remaining = gemini_quota_manager.get_remaining_seconds(self.model_name, "brain")
            return BrainResult(
                text=f"Gemini is cooling down, Sir. Please try again in a moment ({remaining}s remaining).",
                provider=self.provider_id
            )
            
        try:
            sys_instruction = (
                f"You are JARVIS M7, a futuristic Windows-first AI operating system inspired by Tony Stark's assistant. "
                f"You MUST address the user as '{salutation}' in every response. "
                f"Keep your responses concise, intellectual, and slightly robotic yet premium. "
                f"If the user asks you to perform an action, describe what you did or are about to do."
            )
            
            from services.brain.base import format_user_facts_for_prompt, get_uncertainty_guardrail
            sys_instruction += format_user_facts_for_prompt()
            sys_instruction += get_uncertainty_guardrail()
            
            contents = []
            if history:
                for h in history:
                    role = "user" if h["role"] == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=h["content"])]
                        )
                    )
            
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)]
                )
            )
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruction,
                    temperature=0.7
                )
            )
            
            reply = response.text.strip()
            return BrainResult(text=reply, provider=self.provider_id)
            
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                from services.gemini_quota_manager import gemini_quota_manager, extract_retry_delay_seconds
                retry_seconds = extract_retry_delay_seconds(error_text)
                gemini_quota_manager.set_cooldown(self.model_name, retry_seconds, "brain")
                return BrainResult(
                    text="Gemini quota is temporarily exhausted, Sir. I will use offline controls until it resets.",
                    provider=self.provider_id
                )
            logger.error(f"Gemini GenAI execution error: {e}", exc_info=True)
            return BrainResult(
                text=f"I encountered a communication issue, {salutation}. The details are logged in the console.",
                provider=self.provider_id
            )

    def think_stream(self, text: str, history: list[dict] = None):
        if not self.client:
            self.check_configuration()
            
        salutation = config.salutation
        
        if not self.client:
            yield f"I am currently offline as the Gemini API key is missing. Please configure it in settings, {salutation}."
            return

        from services.gemini_quota_manager import gemini_quota_manager
        if not gemini_quota_manager.is_available(self.model_name, "brain"):
            remaining = gemini_quota_manager.get_remaining_seconds(self.model_name, "brain")
            yield f"Gemini is cooling down, Sir. Please try again in a moment ({remaining}s remaining)."
            return
            
        try:
            sys_instruction = (
                f"You are JARVIS M7, a futuristic Windows-first AI operating system inspired by Tony Stark's assistant. "
                f"You MUST address the user as '{salutation}' in every response. "
                f"Keep your responses concise, intellectual, and slightly robotic yet premium. "
                f"If the user asks you to perform an action, describe what you did or are about to do."
            )
            
            from services.brain.base import format_user_facts_for_prompt, get_uncertainty_guardrail
            sys_instruction += format_user_facts_for_prompt()
            sys_instruction += get_uncertainty_guardrail()
            
            contents = []
            if history:
                for h in history:
                    role = "user" if h["role"] == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=h["content"])]
                        )
                    )
            
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)]
                )
            )
            
            response_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruction,
                    temperature=0.7
                )
            )
            
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
            
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                from services.gemini_quota_manager import gemini_quota_manager, extract_retry_delay_seconds
                retry_seconds = extract_retry_delay_seconds(error_text)
                gemini_quota_manager.set_cooldown(self.model_name, retry_seconds, "brain")
                yield "Gemini quota is temporarily exhausted, Sir. I will use offline controls until it resets."
                return
            logger.error(f"Gemini GenAI streaming execution error: {e}", exc_info=True)
            yield f"I encountered a communication issue, {salutation}. The details are logged in the console."
