import json
import os
from services.intent.intent_provider import BaseIntentProvider, IntentResult
from core.config import config
from core.logger import logger
from google import genai
from google.genai import types

class GeminiIntentProvider(BaseIntentProvider):
    @property
    def provider_id(self) -> str:
        return 'gemini'
    def parse_intent(self, text: str) -> IntentResult:
        from services.gemini_quota_manager import gemini_quota_manager, extract_retry_delay_seconds
        model_name = 'gemini-2.5-flash'
        if not gemini_quota_manager.is_available(model_name, "brain"):
            logger.info("Gemini NLU / Brain is cooling down. Skipping Gemini intent parse.")
            return IntentResult('unknown', '', 0.0)

        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('GEMINI_API_KEY') or config.get('gemini_api_key', '')
        if not api_key:
            raise ValueError('Gemini API Key missing')

        client = genai.Client(api_key=api_key)
        
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
            f"Current local time: {current_time} (timezone: {get_local_timezone_name()})\n\n"
            f"User input: {text}\n"
            "Return JSON matching allowed schema."
        )

        logger.info('Requesting NLU intent classification from Gemini for: ' + text)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                retry_seconds = extract_retry_delay_seconds(err_str)
                gemini_quota_manager.set_cooldown(model_name, retry_seconds, "brain")
                logger.warning(f"Gemini intent parse hit rate limit. Cooldown set for {retry_seconds}s.")
            logger.error('Failed to generate Gemini intent response: ' + err_str)
            return IntentResult('unknown', '', 0.0)

        try:
            cleaned = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(cleaned)
            return IntentResult(
                action=data.get('action', 'unknown'),
                target=data.get('target', ''),
                confidence=float(data.get('confidence', 0.5)),
                requires_confirmation=bool(data.get('requires_confirmation', False))
            )
        except Exception as e:
            logger.error('Failed to parse Gemini intent response: ' + str(e))
            return IntentResult('unknown', '', 0.0)


    def health(self) -> tuple[bool, str]:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('GEMINI_API_KEY') or config.get('gemini_api_key', '')
        if not api_key:
            return False, 'API Key missing'
        return True, 'Ready'
