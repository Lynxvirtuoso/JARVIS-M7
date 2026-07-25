"""
test_question_classifier.py
Unit tests for QuestionClassifier & BrainRouter RoutingDecision (Phase 2.5b Goal 1).
"""

import unittest
from services.conversation.question_classifier import question_classifier, QuestionClassifier
from services.brain.router import brain_router, RoutingDecision


class TestQuestionClassifierAndRouting(unittest.TestCase):

    def setUp(self):
        self.classifier = QuestionClassifier()

    def test_wh_question_classification(self):
        res = self.classifier.classify("what is the capital of France?")
        self.assertEqual(res.question_type, "wh_question")
        self.assertTrue(res.is_conversational)
        self.assertFalse(res.requires_tools)
        self.assertEqual(res.estimated_complexity, "LOW")

    def test_aux_question_classification(self):
        res = self.classifier.classify("can you explain about football?")
        self.assertEqual(res.question_type, "aux_question")
        self.assertTrue(res.is_conversational)
        self.assertEqual(res.estimated_complexity, "LOW")

    def test_multi_tool_intent_high_complexity(self):
        res = self.classifier.classify("check my calendar and remind me to call John if I'm free")
        self.assertTrue(res.routing_hints["multi_step_detected"])
        self.assertEqual(res.estimated_complexity, "HIGH")
        self.assertIn("Calendar", res.candidate_skills)
        self.assertIn("Reminder", res.candidate_skills)

    def test_routing_decision_single_agent_fast_path(self):
        decision = brain_router.route("what is the time now")
        self.assertEqual(decision.route, "SINGLE_AGENT")
        self.assertEqual(decision.policy_applied, "fast_path")
        self.assertEqual(decision.starting_provider, "groq")

    def test_routing_decision_multi_agent_tool_chain(self):
        cmd = "check my calendar and remind me to call John if I'm free"
        decision = brain_router.route(cmd)
        self.assertEqual(decision.route, "MULTI_AGENT")
        self.assertEqual(decision.policy_applied, "tool_chain")
        self.assertEqual(decision.starting_provider, "multi_agent")
        self.assertIn("Calendar", decision.selected_skills)

    def test_routing_decision_developer_override(self):
        decision = brain_router.route("multi_agent: research quantum physics")
        self.assertEqual(decision.route, "MULTI_AGENT")
        self.assertIn("developer override", decision.reason)
        self.assertEqual(decision.policy_applied, "research_synthesis")


if __name__ == "__main__":
    unittest.main()
