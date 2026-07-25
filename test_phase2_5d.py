"""
test_phase2_5d.py
Phase 2.5d Multi-Agent Reasoning Architecture Unit Tests for JARVIS M7.

Verifies:
1. Routing Profiles (SIMPLE, RESEARCH, TOOL, FULL_REASONING) expand to exact expected agent lists.
2. Planner Contract Violation (hard check rejecting direct tool_call or response payloads).
3. AgentInput / AgentOutput conformance across all five agents.
4. ToolAgent makes ZERO LLM calls (deterministic TEL integration).
5. Critic verdict retry-cap enforcement (bounded by MAX_REVISION_CAP=1).
"""

import unittest

from services.tools.models import (
    AgentRole, RoutingProfile, CritiqueVerdict, AgentInput, AgentOutput,
    AgentStepStatus, AgentStep
)
from services.brain.router import BrainRouter, RoutingDecision
from services.agents.planner import PlannerAgent, PlannerContractViolation
from services.agents.research import ResearchAgent
from services.agents.tool import ToolAgent
from services.agents.critic import CriticAgent
from services.agents.synthesizer import SynthesizerAgent
from services.agents.coordinator import agent_coordinator, MAX_REVISION_CAP


class TestPhase25dArchitecture(unittest.TestCase):

    def test_routing_profile_expansions(self):
        """Confirm BrainRouter.expand_profile expands each RoutingProfile to exact agent list."""
        self.assertEqual(BrainRouter.expand_profile(RoutingProfile.SIMPLE), [AgentRole.SYNTHESIZER])
        self.assertEqual(BrainRouter.expand_profile(RoutingProfile.RESEARCH), [AgentRole.RESEARCH, AgentRole.SYNTHESIZER])
        self.assertEqual(BrainRouter.expand_profile(RoutingProfile.TOOL), [AgentRole.TOOL, AgentRole.SYNTHESIZER])
        self.assertEqual(
            BrainRouter.expand_profile(RoutingProfile.FULL_REASONING),
            [AgentRole.PLANNER, AgentRole.RESEARCH, AgentRole.TOOL, AgentRole.CRITIC, AgentRole.SYNTHESIZER]
        )

    def test_planner_contract_violation(self):
        """Confirm PlannerAgent raises PlannerContractViolation if direct tool_call or response payload is provided."""
        planner = PlannerAgent()
        agent_input = AgentInput(request="Perform action")

        # Test tool_call in step_params
        with self.assertRaises(PlannerContractViolation):
            planner.run(agent_input, step_params={"tool_call": "calc.exe"})

        # Test response in step_params
        with self.assertRaises(PlannerContractViolation):
            planner.run(agent_input, step_params={"response": "Direct answer"})

        # Test tool_call in execution_constraints
        input_violation = AgentInput(request="Perform action", execution_constraints={"tool_call": "notepad"})
        with self.assertRaises(PlannerContractViolation):
            planner.run(input_violation, step_params={})

    def test_agent_input_output_conformance(self):
        """Confirm all 5 agents accept AgentInput and return conforming AgentOutput."""
        agents = [
            PlannerAgent(),
            ResearchAgent(),
            ToolAgent(),
            CriticAgent(),
            SynthesizerAgent()
        ]
        sample_input = AgentInput(
            request="Test request",
            shared_context={"raw_command": "Test request", "request_id": "req-test-101"},
            memory={"user_facts": ["fact1"]},
            previous_outputs={"step_1": "prev output"},
            execution_constraints={}
        )

        for agent in agents:
            out = agent.run(sample_input, step_params={})
            self.assertIsInstance(out, AgentOutput)
            self.assertIsInstance(out.agent_role, AgentRole)
            self.assertIsInstance(out.reasoning, str)
            self.assertIsInstance(out.structured_result, dict)
            self.assertIsInstance(out.confidence, float)
            self.assertIn(out.status, [AgentStepStatus.SUCCESS, AgentStepStatus.FAILED, AgentStepStatus.SKIPPED])

    def test_tool_agent_zero_llm_calls(self):
        """Regression test proving ToolAgent makes ZERO LLM calls (pure deterministic execution)."""
        tool_agent = ToolAgent()
        agent_input = AgentInput(
            request="Check status",
            shared_context={"tool_call_requests": None}
        )
        
        # Intercept brain think_stream to ensure it is never called
        from core.brain import brain
        original_think_stream = brain.think_stream
        llm_called = False

        def spy_think_stream(*args, **kwargs):
            nonlocal llm_called
            llm_called = True
            return original_think_stream(*args, **kwargs)

        brain.think_stream = spy_think_stream
        try:
            out = tool_agent.run(agent_input, step_params={})
            self.assertFalse(llm_called, "ToolAgent must NOT invoke LLM provider!")
            self.assertEqual(out.agent_role, AgentRole.TOOL)
            self.assertEqual(out.confidence, 1.0)
        finally:
            brain.think_stream = original_think_stream

    def test_critic_verdict_and_retry_cap(self):
        """Verify CriticAgent returns CritiqueVerdict in structured_result and AgentCoordinator respects revision cap."""
        critic = CriticAgent()
        agent_input = AgentInput(
            request="Verify data",
            shared_context={"research_findings": "incomplete data"}
        )
        
        # Test NEEDS_REVISION verdict
        out_rev = critic.run(agent_input, step_params={"request_revision": True})
        self.assertEqual(out_rev.structured_result.get("verdict"), CritiqueVerdict.NEEDS_REVISION.value)
        self.assertLess(out_rev.confidence, 0.5)

        # Test PASSED verdict
        out_pass = critic.run(agent_input, step_params={})
        self.assertEqual(out_pass.structured_result.get("verdict"), CritiqueVerdict.PASSED.value)
        self.assertGreater(out_pass.confidence, 0.8)

        # Test Coordinator retry cap (MAX_REVISION_CAP=1)
        req_id = "req-cap-test"
        res = agent_coordinator.run(
            req_id,
            "check my calendar and remind me to call John if I'm free",
            executor_overrides={"step_critic": {"request_revision": True}}
        )
        self.assertLessEqual(res.revision_count, MAX_REVISION_CAP)


if __name__ == "__main__":
    unittest.main()
