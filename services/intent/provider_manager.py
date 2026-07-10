from core.config import config
from core.logger import logger
from services.intent.gemini_intent_provider import GeminiIntentProvider
from services.intent.openai_intent_provider import OpenAIIntentProvider
from services.intent.intent_provider import IntentResult

class IntentProviderManager:
    def __init__(self):
        self.providers = {
            'gemini': GeminiIntentProvider(),
            'openai': OpenAIIntentProvider()
        }

    def parse_intent(self, text: str) -> IntentResult:
        enable_cloud = config.get('enable_cloud_intent', 'false').lower() == 'true'
        if not enable_cloud:
            return IntentResult('unknown', '', 0.0)

        selected = config.get('intent_provider', 'none').lower()
        if selected not in self.providers:
            return IntentResult('unknown', '', 0.0)

        provider = self.providers[selected]
        is_healthy, _ = provider.health()
        if not is_healthy:
            logger.warn(f'Intent provider {selected} is unhealthy.')
            return IntentResult('unknown', '', 0.0)

        try:
            return provider.parse_intent(text)
        except Exception as e:
            logger.error(f'Failed to parse intent via {selected}: {e}')
            return IntentResult('unknown', '', 0.0)

intent_manager = IntentProviderManager()
