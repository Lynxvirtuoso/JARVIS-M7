import re
from core.database import db
from core.logger import logger
from services.brain.provider_manager import brain_manager, BrainRequest


def needs_web_search(text: str) -> bool:
    """
    Returns True if the text indicates a query requiring real-time web search.
    Default is False.
    """
    text_lower = text.lower().strip()
    
    prefix_patterns = [
        r"^can you\b", r"^could you\b", r"^would you\b", r"^will you\b",
        r"^have you\b", r"^do you know\b", r"^don't you\b",
        r"^dont you\b", r"^please\b",
    ]
    for prefix in prefix_patterns:
        text_lower = re.sub(prefix, "", text_lower).strip()

    # Specific live/current search categories with word boundaries
    live_phrases = [
        r"\btoday\b", r"\blatest\b", r"\bcurrently\b", r"\bright now\b", r"\brecent\b",
        r"\bnews\b", r"\bweather\b", r"\bprice\b", r"\bscore\b", r"\bschedule\b", r"\bstock\b",
        r"\bexchange rate\b", r"\blive\b", r"\bwho is the current\b", r"\bwhat happened today\b",
        r"\bthis week\b", r"\bthis month\b", r"\bnew release\b", r"\blatest version\b",
        r"\bcurrent (price|weather|president|ceo|leader|version|status|score|news)\b",
        r"\b(doing|happening|going on)\s+currently\b"
    ]

    for pattern in live_phrases:
        if re.search(pattern, text_lower):
            return True

    return False


class AIBrain:
    """
    JARVIS Natural Language NLU layer delegating to the BrainProviderManager.
    Maintains history context from SQLite database.
    """
    def think(self, command: str, request_metadata: BrainRequest = None) -> str:
        """
        Sends the command + context history to the active Brain provider and retrieves response.
        """
        history = db.get_history(limit=10)
        req = request_metadata if isinstance(request_metadata, BrainRequest) else BrainRequest(text=command)

        result = brain_manager.think(req, history)
        reply_text = result.text if hasattr(result, "text") and result.text else ""
        
        if reply_text:
            db.add_history("user", command)
            db.add_history("model", reply_text)
        
        return reply_text

    def think_stream(self, command: str, request_metadata: BrainRequest = None):
        """
        Yields tokens from the active Brain provider chunk-by-chunk.
        """
        history = db.get_history(limit=10)
        req = request_metadata if isinstance(request_metadata, BrainRequest) else BrainRequest(text=command)
        yield from brain_manager.think_stream(req, history)


# Global brain instance
brain = AIBrain()
