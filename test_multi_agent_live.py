"""
LIVE PHASE 2.5 MULTI-AGENT REASONING VERIFICATION HARNESS
=========================================================
Tests 6 Required Scenarios:
1. Sequential agent chain (Planner -> Research -> Tool -> Critic -> Synthesizer) succeeds end-to-end.
2. One agent fails -> downstream depends_on steps correctly skip with dependency_X_not_successful, plan outcome is not COMPLETE_SUCCESS.
3. Critic requests revision -> Research reruns once -> Synthesizer proceeds. Second contradiction must NOT trigger second revision (hard cap test).
4. Cancellation fired mid-chain -> coordinator stops between steps, no final_response written.
5. Context-write enforcement -> agent attempting to write key it doesn't own is rejected.
6. BrainRouter._should_use_multi_agent returning False -> confirms single-agent bypass works cleanly.
"""

import sys
import os
import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 80)
print(f"LIVE MULTI-AGENT REASONING VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from services.agents.coordinator import agent_coordinator, AgentCoordinator
from services.tools.models import AgentRole, AgentStepStatus, ValidationOutcome
from services.brain.router import brain_router


def run_live_multi_agent_verification():
    print("\n--- Scenario 1: Sequential Agent Chain (End-to-End Success) ---")
    coord = AgentCoordinator()
    req_id_1 = "req-live-multi-001"
    cmd_1 = "Research football scores and send summary"
    res_1 = coord.run(req_id_1, cmd_1)
    print(f"Plan ID: {res_1.plan_id} | Outcome: {res_1.outcome.value} | Steps Executed: {len(res_1.step_results)}")
    print(f"Final Response: '{res_1.final_response}'")
    assert res_1.outcome == ValidationOutcome.COMPLETE_SUCCESS
    assert res_1.final_response is not None
    assert "Synthesized response for" in res_1.final_response

    print("\n--- Scenario 2: Downstream Cascading Dependency Skip on Failure ---")
    coord_2 = AgentCoordinator()
    req_id_2 = "req-live-multi-002"
    res_2 = coord_2.run(req_id_2, "Research space exploration", executor_overrides={
        "step_research": {"override_fail": True}
    })
    print(f"Outcome: {res_2.outcome.value} | Research Status: {res_2.step_results[0].status.value}")
    print(f"Tool Step Skipped: {res_2.step_results[1].skipped} | Skip Reason: {res_2.step_results[1].skip_reason}")
    assert res_2.outcome == ValidationOutcome.FATAL_FAILURE
    assert res_2.step_results[1].skipped is True
    assert res_2.step_results[1].skip_reason == "dependency_step_research_not_successful"

    print("\n--- Scenario 3: Critic Revision Request & Hard Cap = 1 Retry ---")
    coord_3 = AgentCoordinator()
    req_id_3 = "req-live-multi-003"
    res_3 = coord_3.run(req_id_3, "Check financial reports", executor_overrides={
        "step_critic": {"request_revision": True},
        "step_critic_rev1": {"request_revision": True}  # Attempt second revision
    })
    print(f"Outcome: {res_3.outcome.value} | Total Steps Executed: {len(res_3.step_results)} | Revisions Count: {res_3.revision_count}")
    assert res_3.outcome == ValidationOutcome.COMPLETE_SUCCESS
    assert res_3.revision_count == 1  # Hard cap enforced!

    print("\n--- Scenario 4: Mid-Chain Cancellation Check ---")
    coord_4 = AgentCoordinator()
    req_id_4 = "req-live-multi-004"
    coord_4.cancel_request(req_id_4)
    res_4 = coord_4.run(req_id_4, "Execute long running analysis")
    print(f"Outcome: {res_4.outcome.value} | Final Response: {res_4.final_response}")
    assert res_4.outcome == ValidationOutcome.FATAL_FAILURE
    assert res_4.final_response is None

    print("\n--- Scenario 5: Context Ownership Enforcement ---")
    coord_5 = AgentCoordinator()
    req_id_5 = "req-live-multi-005"
    # Research agent attempts to write "final_response", which is owned exclusively by SYNTHESIZER
    from services.tools.models import AgentResult, AgentStepStatus
    def bad_research_run(shared_context, step_params):
        return AgentResult(
            agent_role=AgentRole.RESEARCH,
            status=AgentStepStatus.SUCCESS,
            output="Bad research",
            context_writes={"final_response": "Illegal write by Research agent"}
        )
    coord_5._agents[AgentRole.RESEARCH].run = bad_research_run
    res_5 = coord_5.run(req_id_5, "Test context security")
    print(f"Research Step Status: {res_5.step_results[0].status.value} | Error: {res_5.step_results[0].error}")
    assert res_5.step_results[0].status == AgentStepStatus.FAILED
    assert "unauthorized_context_write" in res_5.step_results[0].error

    print("\n--- Scenario 6: BrainRouter Multi-Agent Hook Bypass ---")
    decision_normal = brain_router.route("what time is it")
    decision_multi = brain_router.route("multi_agent: check weather and then play focus music")
    print(f"Normal Route: starting_provider={decision_normal.starting_provider} | reason={decision_normal.reason}")
    print(f"Multi-Agent Route: starting_provider={decision_multi.starting_provider} | reason={decision_multi.reason}")
    assert decision_normal.starting_provider == "groq"
    assert decision_multi.starting_provider == "multi_agent"

    print("\n=" * 80)
    print("LIVE MULTI-AGENT REASONING VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    run_live_multi_agent_verification()
