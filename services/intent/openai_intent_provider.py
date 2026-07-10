import json
import os
import requests
from services.intent.intent_provider import BaseIntentProvider, IntentResult
from core.config import config
from core.logger import logger

class OpenAIIntentProvider(BaseIntentProvider):
    @property
    def provider_id(self) -> str:
        return 'openai'

    def parse_intent(self, text: str) -> IntentResult:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY') or config.get('openai_api_key', '')
        if not api_key:
            raise ValueError('OpenAI API Key missing')

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        system_instruction = (
            "You are the intent normalizer for a Windows personal assistant named JARVIS.\n\n"
            "Convert the user's command into safe structured JSON only.\n\n"
            "Do not invent shell commands.\n"
            "Do not invent executable names.\n"
            "Do not include explanations.\n"
            "Do not execute anything.\n\n"
            "Allowed actions:\n"
            "open_app, close_app, search_app, open_website, volume, screenshot, sleep_hud, full_exit, ask_general, unknown.\n\n"
            "Known app names are supplied separately by the local app resolver.\n\n"
            "If the user wants to open or close an app, return the app name exactly as spoken by the user. The local app resolver will decide the executable.\n\n"
            "Return JSON only:\n"
            "{\n"
            "  \"action\": \"...\",\n"
            "  \"target\": \"...\",\n"
            "  \"confidence\": 0.0,\n"
            "  \"requires_confirmation\": false\n"
            "}"
        )

        payload = {
            'model': 'gpt-4o-mini',
            'messages': [
                {'role': 'system', 'content': system_instruction},
                {'role': 'user', 'content': text}
            ],
            'temperature': 0.1,
            'response_format': {'type': 'json_object'}
        }

        logger.info('Requesting NLU intent classification from OpenAI for: ' + text)
        try:
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                raise RuntimeError(f'OpenAI API error: {response.status_code} - {response.text}')

            res_data = response.json()
            content = res_data['choices'][0]['message']['content'].strip()
            cleaned = content.replace('```json', '').replace('```', '').strip()
            data = json.loads(cleaned)
            return IntentResult(
                action=data.get('action', 'unknown'),
                target=data.get('target', ''),
                confidence=float(data.get('confidence', 0.5)),
                requires_confirmation=bool(data.get('requires_confirmation', False))
            )
        except Exception as e:
            logger.error('Failed to parse OpenAI intent response: ' + str(e))
            return IntentResult('unknown', '', 0.0)

    def health(self) -> tuple[bool, str]:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY') or config.get('openai_api_key', '')
        if not api_key:
            return False, 'API Key missing'
        return True, 'Ready'
