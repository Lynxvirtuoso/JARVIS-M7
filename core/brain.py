from core.database import db
from services.brain.provider_manager import brain_manager
import re

from core.logger import logger

def needs_web_search(text: str) -> bool:
    """
    Returns True if the text indicates a query requiring real-time web search.
    """
    text_lower = text.lower().strip()
    
    prefix_patterns = [
        r"^can you\b", r"^could you\b", r"^would you\b", r"^will you\b",
        r"^have you\b", r"^do you know\b", r"^don't you\b",
        r"^dont you\b", r"^please\b",
    ]
    for prefix in prefix_patterns:
        text_lower = re.sub(prefix, "", text_lower).strip()
    
    # 1. Expanded keyword categories
    sports = ["score", "won", "winner", "match", "game", "tournament", "championship", "final", "playoffs", "standings", "ranking"]
    finance = ["price", "stock", "market", "exchange rate", "crypto", "bitcoin", "value of"]
    news = ["news", "headline", "breaking", "happened", "announcement", "release", "launch", "update"]
    time_relative = ["current", "latest", "today", "this week", "this month", "this year", "right now", "recently", "yesterday", "as of", "up to date", "nowadays"]
    roles = ["current president", "current ceo", "who is the current", "who leads"]
    direct = ["search", "google", "look up", "find out"]

    search_terms = sports + finance + news + time_relative + roles + direct
    for term in search_terms:
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text_lower):
            return True

    # 2. Evergreen / conceptual exclusions
    evergreen_patterns = [
        r"\bwhy is\b",
        r"\bhow does\b.*\bwork\b",
        r"\bexplain\b",
        r"\bwhat is the definition of\b",
        r"\bhow do magnets\b",
        r"\bwhat causes\b"
    ]
    for pattern in evergreen_patterns:
        if re.search(pattern, text_lower):
            return False

    # 3. Default safety net (default to search) with tracking log
    logger.info(f"needs_web_search: safety-net default triggered for: {text}")
    return True

class AIBrain:
    """
    JARVIS Natural Language NLU layer delegating to the BrainProviderManager.
    Maintains history context from SQLite database.
    """
    def think(self, command: str) -> str:
        """
        Sends the command + context history to the active Brain provider and retrieves response.
        """
        # Retrieve last 10 turns of history
        history = db.get_history(limit=10)
        
        if needs_web_search(command):
            groq_provider = brain_manager.providers.get("groq")
            if groq_provider and hasattr(groq_provider, "think_compound_mini"):
                try:
                    result_text = "".join(list(groq_provider.think_compound_mini(command, history)))
                    db.add_history("user", command)
                    db.add_history("model", result_text)
                    return result_text
                except Exception as e:
                    from core.logger import logger
                    logger.error(f"groq/compound-mini think failed, falling back: {e}")

        result = brain_manager.think(command, history)
        
        # Save history to SQLite
        db.add_history("user", command)
        db.add_history("model", result.text)
        
        return result.text

    def think_stream(self, command: str):
        """
        Yields tokens from the active Brain provider chunk-by-chunk.
        """
        history = db.get_history(limit=10)
        if needs_web_search(command):
            groq_provider = brain_manager.providers.get("groq")
            if groq_provider and hasattr(groq_provider, "think_compound_mini"):
                try:
                    yield from groq_provider.think_compound_mini(command, history)
                    return
                except Exception as e:
                    from core.logger import logger
                    logger.error(f"groq/compound-mini think_stream failed, falling back: {e}")
        yield from brain_manager.think_stream(command, history)

# Global brain instance
brain = AIBrain()

