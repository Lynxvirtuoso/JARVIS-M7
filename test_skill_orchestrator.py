"""
test_skill_orchestrator.py
Unit test suite for Phase 2.4 SkillOrchestrator.
Verifies single-skill bypass (zero regression), sequential plan creation,
conditional plan creation, and data-handoff context wiring.
"""

import unittest
from services.skills.orchestrator import SkillOrchestrator


class TestSkillOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = SkillOrchestrator()

    def test_single_skill_bypass(self):
        # Single skill command should return None
        plan = self.orchestrator.plan_request("req-1", "open calculator")
        self.assertIsNone(plan)

    def test_sequential_plan_creation(self):
        cmd = "check my calendar, then play my focus playlist"
        plan = self.orchestrator.plan_request("req-seq-101", cmd)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tool_name, "calendar_tool")
        self.assertEqual(plan.steps[1].tool_name, "media_tool")
        self.assertEqual(plan.steps[1].depends_on, "step_1")
        self.assertEqual(plan.metadata["pattern"], "sequential")

    def test_conditional_plan_creation(self):
        cmd = "if I'm free after 5pm, remind me to call John"
        plan = self.orchestrator.plan_request("req-cond-102", cmd)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].depends_on, "step_1")
        self.assertEqual(plan.steps[1].condition, "is_free_after_1700")
        self.assertEqual(plan.metadata["pattern"], "conditional")

    def test_conditional_plan_execution_false_condition_skips(self):
        from services.tools.tool_execution_layer import tool_execution_layer
        from services.tools.models import ValidationOutcome
        cmd = "if I'm free after 5pm, remind me to call John"
        plan = self.orchestrator.plan_request("req-cond-false-103", cmd)

        # Context has is_free_after_1700 set to False
        plan.context["is_free_after_1700"] = False

        res = tool_execution_layer.execute_plan(plan)
        self.assertEqual(res.outcome, ValidationOutcome.COMPLETE_SUCCESS)
        self.assertTrue(res.step_results[1].skipped)
        self.assertEqual(res.step_results[1].skip_reason, "condition_is_free_after_1700_false")
        self.assertIn("not free after 5 PM", res.spoken_summary)

    def test_dependency_failure_skips_downstream_step(self):
        from services.tools.tool_execution_layer import tool_execution_layer
        from services.tools.models import ValidationOutcome
        cmd = "check my calendar, then play my focus playlist"
        plan = self.orchestrator.plan_request("req-dep-fail-104", cmd)

        # Simulate step_1 failing
        def failing_step_1(params):
            raise RuntimeError("Calendar DB unavailable")

        res = tool_execution_layer.execute_plan(plan, executor_override={"step_1": failing_step_1})
        self.assertEqual(res.outcome, ValidationOutcome.FATAL_FAILURE)
        self.assertFalse(res.step_results[0].success)
        self.assertTrue(res.step_results[1].skipped)
        self.assertEqual(res.step_results[1].skip_reason, "dependency_step_1_not_successful")
        self.assertIn("skipped because its dependency step_1 failed", res.spoken_summary)

    def test_data_handoff_plan_creation(self):
        cmd = "find today's meeting notes and summarize them"
        plan = self.orchestrator.plan_request("req-handoff-103", cmd)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].depends_on, "step_1")
        self.assertIn("meeting_notes_content", plan.context)
        self.assertEqual(plan.metadata["pattern"], "data_handoff")


if __name__ == "__main__":
    unittest.main()
