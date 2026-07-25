"""
test_tool_execution_layer.py
Unit test suite for Phase 2.3 Tool Execution Layer (TEL).
Verifies sequential ExecutionPlan execution under single request_id,
TrustGate plan confirmation evaluation, mid-chain cancellation checks,
outcome classification, and spoken explanation generation.
"""

import unittest
from services.tools.models import ExecutionPlan, ToolStep, ValidationOutcome
from services.tools.tool_execution_layer import ToolExecutionLayer
from core.trust_gate import TrustGate


class TestToolExecutionLayer(unittest.TestCase):

    def setUp(self):
        self.tel = ToolExecutionLayer()

    def test_complete_success_execution(self):
        plan = ExecutionPlan(
            plan_id="plan-1",
            request_id="req-1001",
            steps=[
                ToolStep(step_id="s1", tool_name="system_control", action="check_status"),
                ToolStep(step_id="s2", tool_name="file_system", action="read_file"),
            ],
        )

        result = self.tel.execute_plan(plan)
        self.assertEqual(result.outcome, ValidationOutcome.COMPLETE_SUCCESS)
        self.assertEqual(len(result.step_results), 2)
        self.assertTrue("Successfully executed" in result.spoken_summary)

    def test_trust_gate_plan_evaluation(self):
        plan = ExecutionPlan(
            plan_id="plan-destructive",
            request_id="req-1002",
            steps=[
                ToolStep(step_id="s1", tool_name="file_system", action="delete_file", destructive=True),
                ToolStep(step_id="s2", tool_name="email_tool", action="send_email", destructive=True),
            ],
        )

        confirmation = TrustGate.evaluate_plan(plan)
        self.assertTrue(confirmation.requires_confirmation)
        self.assertEqual(len(confirmation.confirmations_required), 2)
        self.assertEqual(len(confirmation.destructive_steps), 2)

    def test_mid_chain_cancellation(self):
        plan = ExecutionPlan(
            plan_id="plan-cancel",
            request_id="req-cancel-101",
            steps=[
                ToolStep(step_id="s1", tool_name="system_control", action="check_status"),
                ToolStep(step_id="s2", tool_name="file_system", action="delete_file", destructive=True),
            ],
        )

        # Flag request as cancelled prior to execution
        self.tel.request_cancel("req-cancel-101")
        result = self.tel.execute_plan(plan)

        self.assertEqual(result.outcome, ValidationOutcome.FATAL_FAILURE)
        self.assertEqual(len(result.step_results), 1)
        self.assertFalse(result.step_results[0].success)
        self.assertTrue("cancelled" in result.spoken_summary.lower())

    def test_partial_success_spoken_explanation(self):
        plan = ExecutionPlan(
            plan_id="plan-partial",
            request_id="req-partial-102",
            steps=[
                ToolStep(step_id="s1", tool_name="file_system", action="find_file"),
                ToolStep(step_id="s2", tool_name="email_tool", action="send_email"),
            ],
        )

        # Override handler for s2 to simulate failure
        def failing_handler(params):
            raise RuntimeError("SMTP connection timeout")

        result = self.tel.execute_plan(plan, executor_override={"s2": failing_handler})

        self.assertEqual(result.outcome, ValidationOutcome.PARTIAL_SUCCESS)
        self.assertTrue("completed steps for file_system, but failed to complete email_tool" in result.spoken_summary)


if __name__ == "__main__":
    unittest.main()
