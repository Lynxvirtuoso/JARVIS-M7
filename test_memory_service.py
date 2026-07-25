"""
test_memory_service.py
Unit test suite for Phase 2.6 MemoryService & SessionMemoryStore.
Verifies MemoryService facade dispatch, SessionMemoryStore lifecycle,
and refactored memory handlers.
"""

import unittest
from services.memory.memory_service import memory_service, MemoryService, SessionMemoryStore


class TestMemoryService(unittest.TestCase):

    def setUp(self):
        memory_service.clear_all_facts()
        memory_service.clear_session()

    def test_fact_store_dispatch(self):
        memory_service.set_fact("user_facts", ["likes tea", "location: London"])
        facts = memory_service.get_fact("user_facts", default=[])
        self.assertEqual(len(facts), 2)
        self.assertIn("likes tea", facts)

        # Confirm exact parity with underlying db
        from core.database import db
        db_facts = db.get_memory("user_facts", default=[])
        self.assertEqual(db_facts, facts)

    def test_session_memory_store_lifecycle(self):
        store = SessionMemoryStore()
        store.set("current_space", "music")
        self.assertEqual(store.get("current_space"), "music")
        
        store.clear()
        self.assertIsNone(store.get("current_space"))

    def test_memory_service_session_delegation(self):
        memory_service.set_session_val("current_space", "music")
        self.assertEqual(memory_service.get_session_val("current_space"), "music")

        memory_service.clear_session()
        self.assertIsNone(memory_service.get_session_val("current_space"))

    def test_history_store_dispatch(self):
        memory_service.add_history("Hello JARVIS", "Hello Sir")
        history = memory_service.get_history(limit=1)
        self.assertGreaterEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
