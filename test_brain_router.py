"""
test_brain_router.py
Unit test suite for Phase 2.2 BrainRouter.
Verifies synchronous CPU-only routing decisions, privacy mode starting tier,
feature-flagged confidence escalation, and outcome telemetry recording.
"""

import unittest
from services.brain.router import BrainRouter, RoutingDecision


class TestBrainRouter(unittest.TestCase):

    def setUp(self):
        self.router = BrainRouter()

    def test_default_routing_starts_at_groq(self):
        decision = self.router.route("what is the weather today", is_private=False)
        self.assertEqual(decision.starting_provider, "groq")
        self.assertEqual(decision.provider_chain, ["groq", "gemini", "ollama"])
        self.assertEqual(decision.reason, "default")
        self.assertFalse(decision.is_offline)

    def test_privacy_mode_starts_at_ollama(self):
        decision = self.router.route("my confidential query", is_private=True)
        self.assertEqual(decision.starting_provider, "ollama")
        self.assertEqual(decision.provider_chain, ["ollama", "groq", "gemini"])
        self.assertEqual(decision.reason, "privacy_mode")
        self.assertTrue(decision.is_offline)

    def test_confidence_escalation_disabled_by_default(self):
        self.assertFalse(BrainRouter.ENABLE_CONFIDENCE_ESCALATION)
        decision = self.router.route("open calculator", is_private=False, skill_match_confidence=0.95)
        # Should gracefully ignore confidence and use default routing since feature flag is False
        self.assertEqual(decision.starting_provider, "groq")
        self.assertEqual(decision.reason, "default")

    def test_confidence_escalation_enabled_with_graceful_degradation(self):
        try:
            BrainRouter.ENABLE_CONFIDENCE_ESCALATION = True
            # High confidence -> skill escalation
            decision_high = self.router.route("open calculator", skill_match_confidence=0.95)
            self.assertEqual(decision_high.starting_provider, "skill")
            self.assertEqual(decision_high.reason, "high_confidence_skill_match")

            # Missing confidence -> graceful degradation to default
            decision_none = self.router.route("open calculator", skill_match_confidence=None)
            self.assertEqual(decision_none.starting_provider, "groq")
            self.assertEqual(decision_none.reason, "default")
        finally:
            BrainRouter.ENABLE_CONFIDENCE_ESCALATION = False

    def test_record_outcome_updates_stats(self):
        self.router.record_outcome("req-1", "groq", 120.0, True)
        stats = self.router._provider_stats["groq"]
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["successes"], 1)
        self.assertEqual(stats["avg_latency_ms"], 120.0)

        self.router.record_outcome("req-2", "groq", 200.0, True)
        self.assertEqual(stats["total_calls"], 2)
        self.assertEqual(stats["avg_latency_ms"], (120.0 * 0.8) + (200.0 * 0.2))


if __name__ == "__main__":
    unittest.main()
