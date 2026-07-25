"""
test_agent_coordinator.py
Unit test suite for Phase 2.5 AgentCoordinator & Multi-Agent Reasoning.
Verifies plan creation, step execution, dependency enforcement, revision hard cap,
context ownership enforcement, and BrainRouter multi-agent hook bypass.
"""

import unittest
from services.agents.coordinator import AgentCoordinator, MAX_REVISION_CAP
from services.tools.models import AgentRole, AgentStepStatus, ValidationOutcome
from services.brain.router import brain_router


class TestAgentCoordinator(unittest.TestCase):

    def setUp(self):
        self.coordinator = AgentCoordinator()

    def test_sequential_agent_chain_success(self):
        res = self.coordinator.run("req-test-seq-1", "Research and summarize climate data")
        self.assertEqual(res.outcome, ValidationOutcome.COMPLETE_SUCCESS)
        self.assertIsNotNone(res.final_response)
        self.assertEqual(len(res.step_results), 4)

    def test_cascading_dependency_skip_on_agent_failure(self):
        res = self.coordinator.run(
            "req-test-fail-2",
            "Research data",
            executor_overrides={"step_research": {"override_fail": True}}
        )
        self.assertEqual(res.outcome, ValidationOutcome.FATAL_FAILURE)
        self.assertEqual(res.step_results[0].status, AgentStepStatus.FAILED)
        self.assertTrue(res.step_results[1].skipped)
        self.assertEqual(res.step_results[1].skip_reason, "dependency_step_research_not_successful")

    def test_critic_revision_hard_cap(self):
        res = self.coordinator.run(
            "req-test-rev-3",
            "Evaluate market trends",
            executor_overrides={
                "step_critic": {"request_revision": True},
                "step_critic_rev1": {"request_revision": True}
            }
        )
        self.assertEqual(res.outcome, ValidationOutcome.COMPLETE_SUCCESS)
        self.assertEqual(res.revision_count, MAX_REVISION_CAP)
        self.assertEqual(len(res.step_results), 6)  # 4 base + 2 revision steps

    def test_mid_chain_cancellation(self):
        self.coordinator.cancel_request("req-test-cancel-4")
        res = self.coordinator.run("req-test-cancel-4", "Analyze big data")
        self.assertEqual(res.outcome, ValidationOutcome.FATAL_FAILURE)
        self.assertIsNone(res.final_response)

    def test_unauthorized_context_write_rejection(self):
        from services.tools.models import AgentResult
        def bad_agent_run(shared_context, step_params):
            return AgentResult(
                agent_role=AgentRole.RESEARCH,
                status=AgentStepStatus.SUCCESS,
                output="Bad write",
                context_writes={"final_response": "Illegal write"}
            )
        self.coordinator._agents[AgentRole.RESEARCH].run = bad_agent_run
        res = self.coordinator.run("req-test-sec-5", "Test context security")
        self.assertEqual(res.step_results[0].status, AgentStepStatus.FAILED)
        self.assertIn("unauthorized_context_write", res.step_results[0].error)

    def test_brain_router_multi_agent_hook(self):
        dec_single = brain_router.route("open chrome")
        dec_multi = brain_router.route("multi_agent: check weather and then play focus music")
        self.assertEqual(dec_single.starting_provider, "groq")
        self.assertEqual(dec_multi.starting_provider, "multi_agent")


if __name__ == "__main__":
    unittest.main()
