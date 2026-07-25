"""
services/memory/memory_service.py
Phase 2.6 Memory Service Architecture for JARVIS M7.
Thin facade dispatching memory operations across SessionMemoryStore, FactStore, and HistoryStore.
Contains NO caching, NO cross-store merging, and NO independent business logic.
"""

import logging
from typing import Dict, Any, List, Optional
from core.database import db

logger = logging.getLogger(__name__)


class SessionMemoryStore:
    """
    In-memory, session-scoped store for active conversational state.
    Cleared on session end. Not persisted to database.
    """
    def __init__(self):
        self._session_data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._session_data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._session_data[key] = value

    def delete(self, key: str) -> None:
        self._session_data.pop(key, None)

    def clear(self) -> None:
        self._session_data.clear()
        logger.info("[SESSION_MEMORY] SessionMemoryStore cleared.")


class FactStore:
    """
    Wraps existing db.get_memory("user_facts") and db.set_memory("user_facts").
    Provides thin, owned interface over database fact operations.
    """
    MEMORY_KEY = "user_facts"

    def get_facts(self) -> Any:
        return db.get_memory(self.MEMORY_KEY, default=[])

    def get_fact(self, key: str, default: Any = None) -> Any:
        facts = db.get_memory(key, default=default)
        return facts

    def set_fact(self, key: str, value: Any) -> None:
        db.set_memory(key, value)
        logger.info(f"[FACT_STORE] Saved fact '{key}'.")

    def delete_fact(self, key: str) -> bool:
        facts = db.get_memory(self.MEMORY_KEY, default=[])
        if isinstance(facts, list) and key in facts:
            facts.remove(key)
            db.set_memory(self.MEMORY_KEY, facts)
            logger.info(f"[FACT_STORE] Deleted fact '{key}'.")
            return True
        return False

    def clear_facts(self) -> None:
        db.set_memory(self.MEMORY_KEY, [])
        logger.info("[FACT_STORE] All user facts cleared.")


class HistoryStore:
    """
    Wraps existing db.add_history and db.get_history.
    Provides thin, owned interface over database history operations.
    """
    def add_history(self, user_text: str, response_text: str) -> None:
        db.add_history(user_text, response_text)

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return db.get_history(limit=limit)


class MemoryService:
    """
    Thin facade routing memory calls to SessionMemoryStore, FactStore, or HistoryStore.
    Strictly contains NO independent storage, caching, or cross-store merging.
    """
    def __init__(self):
        self.session = SessionMemoryStore()
        self.facts = FactStore()
        self.history = HistoryStore()

    # Fact Store Facade Delegation
    def get_fact(self, key: str, default: Any = None) -> Any:
        return self.facts.get_fact(key, default)

    def set_fact(self, key: str, value: Any) -> None:
        self.facts.set_fact(key, value)

    def delete_fact(self, key: str) -> bool:
        return self.facts.delete_fact(key)

    def get_all_facts(self) -> Dict[str, Any]:
        return self.facts.get_facts()

    def clear_all_facts(self) -> None:
        self.facts.clear_facts()

    # History Store Facade Delegation
    def add_history(self, user_text: str, response_text: str) -> None:
        self.history.add_history(user_text, response_text)

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.history.get_history(limit=limit)

    # Session Memory Delegation
    def get_session_val(self, key: str, default: Any = None) -> Any:
        return self.session.get(key, default)

    def set_session_val(self, key: str, value: Any) -> None:
        self.session.set(key, value)

    def clear_session(self) -> None:
        self.session.clear()


# Global singleton facade instance
memory_service = MemoryService()
