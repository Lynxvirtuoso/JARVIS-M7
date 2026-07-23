import json
from core.config import config
from core.logger import logger
from services.intent.groq_intent_provider import GroqIntentProvider
from services.intent.openai_intent_provider import OpenAIIntentProvider
from services.intent.intent_provider import IntentResult

class IntentProviderManager:
    def __init__(self):
        self.providers = {
            'groq': GroqIntentProvider(),
            'openai': OpenAIIntentProvider()
        }
        self._cache_text = None
        self._cache_result = None

    def clear_cache(self):
        self._cache_text = None
        self._cache_result = None

    def parse_intent(self, text: str) -> IntentResult:
        if self._cache_text == text and self._cache_result is not None:
            logger.info(f"Returning cached NLU intent result for: '{text}' (action: {self._cache_result.action})")
            return self._cache_result

        result = self._parse_intent_uncached(text)
        self._cache_text = text
        self._cache_result = result
        return result

    def _parse_intent_uncached(self, text: str) -> IntentResult:
        selected = config.get('intent_provider', 'groq').lower()
        if selected == 'gemini' or selected == 'none':
            selected = 'groq'
        
        # If intent_provider is not explicitly configured, fall back to active brain provider
        if selected == 'none':
            from services.brain.provider_manager import brain_manager
            try:
                active_brain = brain_manager.get_selected_provider()
                if active_brain:
                    selected = active_brain.provider_id
                    logger.info(f"Falling back to active brain provider '{selected}' for intent parsing.")
            except Exception as e:
                logger.error(f"Failed to fetch active brain provider: {e}")

        if selected in self.providers:
            provider = self.providers[selected]
            is_healthy, _ = provider.health()
            if is_healthy:
                try:
                    res = provider.parse_intent(text)
                    if res and (res.action != 'unknown' or res.confidence > 0.0):
                        return res
                    logger.info(f"NLU provider '{selected}' returned unknown/failed. Falling back to active brain NLU.")
                except Exception as e:
                    logger.error(f'Failed to parse intent via {selected}: {e}')
            else:
                logger.warning(f"Selected NLU provider '{selected}' is unhealthy. Falling back to active brain NLU.")

        # Generic fallback that runs the NLU query using the active Brain provider's API
        try:
            from services.brain.provider_manager import brain_manager
            active_brain = brain_manager.get_selected_provider()
            
            system_instruction = (
                "You are the intent normalizer for a Windows personal assistant named JARVIS.\n\n"
                "Convert the user's command into safe structured JSON only.\n\n"
                "Do not invent shell commands.\n"
                "Do not invent executable names.\n"
                "Do not include explanations.\n"
                "Do not execute anything.\n\n"
                "Allowed actions:\n"
                "open_app, close_app, search_app, open_website, volume, screenshot, sleep_hud, full_exit, ask_general, unknown, "
                "create_event, update_event, delete_event, list_events, get_next_event, check_availability, place_call.\n\n"
                "Known app names are supplied separately by the local app resolver.\n\n"
                "If the user wants to open or close an app, return the app name exactly as spoken by the user. The local app resolver will decide the executable.\n\n"
                "For calendar actions, the 'target' field MUST be a JSON-serialized string containing the parameters:\n"
                "- create_event: {\"summary\": string, \"start_time\": ISO8601_datetime, \"end_time\": ISO8601_datetime, \"description\": string/null, \"location\": string/null, \"attendees\": [string]/null}. IMPORTANT: Do NOT guess/fabricate email addresses. Only populate the attendees array if actual email addresses (containing '@') are explicitly provided in the command. If only names are given, append/put them in the summary (e.g. 'Lunch with Alex') and leave attendees null.\n"
                "- update_event: {\"event_ref\": string, \"updates\": dict}. E.g. updates can contain location, description, or start_time/end_time for time rescheduling. Explicitly recognize rescheduling/time modification verbs like 'move', 'reschedule', 'push to', 'postpone', 'change the time of' as update_event.\n"
                "- delete_event: {\"event_ref\": string}\n"
                "- list_events: {\"time_min\": ISO8601_datetime, \"time_max\": ISO8601_datetime}\n"
                "- get_next_event: {}\n"
                "- check_availability: {\"start_time\": ISO8601_datetime, \"end_time\": ISO8601_datetime}\n\n"
                "For call actions (e.g., 'call Alex', 'phone mom', 'dial +1234567890'), the action is 'place_call' and the 'target' field MUST be a string representing the contact name or query parameter for the person they want to call.\n"
                "Recognize all natural phrasings expressing intent to phone someone, followed by a person/contact name, such as: 'call X', 'call up X', 'make a call to X', 'make me a call to X', 'phone X', 'dial X', 'ring X', 'give X a call', 'get X on the phone', 'can you call X', 'I want to call X', 'place a call to X', 'reach out to X by phone', 'connect me to X', 'try calling X' (where X is the target contact name).\n\n"
                "Return JSON only:"
            )
            
            from services.calendar_service import get_local_timezone_name
            import datetime
            local_tz = datetime.datetime.now().astimezone().tzinfo
            current_time = datetime.datetime.now(local_tz).strftime("%A, %B %d, %Y, %I:%M %p")
            
            prompt = (
                f"System Instruction: {system_instruction}\n\n"
                f"Current local time: {current_time} (timezone: {get_local_timezone_name()})\n\n"
                f"User input: {text}\n"
                "Return JSON matching allowed schema."
            )
            
            logger.info(f"Requesting NLU intent classification from active brain ({active_brain.provider_id}) for: {text}")
            res = active_brain.think(prompt)
            if res and res.text:
                cleaned = res.text.replace('```json', '').replace('```', '').strip()
                data = json.loads(cleaned)
                return IntentResult(
                    action=data.get('action', 'unknown'),
                    target=data.get('target', ''),
                    confidence=float(data.get('confidence', 0.8)),
                    requires_confirmation=bool(data.get('requires_confirmation', False))
                )
        except Exception as e:
            logger.error(f"Fallback intent parsing via active Brain failed: {e}")

        return IntentResult('unknown', '', 0.0)

intent_manager = IntentProviderManager()
