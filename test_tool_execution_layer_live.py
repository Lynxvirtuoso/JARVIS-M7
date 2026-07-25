"""
LIVE TOOL EXECUTION LAYER VERIFICATION HARNESS
==============================================
Verifies live Multi-Step Tool Execution Layer (TEL) behavior:
1. Multi-step chain with 1 destructive step (single combined confirmation).
2. Multi-step chain with 2 distinct irreversible intents (TrustGate plan policy verification).
3. Cancelled mid-chain execution aborting remaining steps.
4. Partial failure case producing audible spoken explanation.
"""

import sys
import os
import time
import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 80)
print(f"LIVE TOOL EXECUTION LAYER VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from services.tools.models import ExecutionPlan, ToolStep, ValidationOutcome
from services.tools.tool_execution_layer import tool_execution_layer
from core.trust_gate import TrustGate

def run_live_tel_verification():
    print("\n--- Test 1: Multi-step chain with 1 destructive step (Single confirmation) ---")
    plan1 = ExecutionPlan(
        plan_id="plan-live-1",
        request_id="req-live-101",
        steps=[
            ToolStep(step_id="s1", tool_name="system_control", action="get_status"),
            ToolStep(step_id="s2", tool_name="file_system", action="delete_cache_file", destructive=True),
        ],
    )
    confirm1 = TrustGate.evaluate_plan(plan1)
    print(f"Plan 1 Confirmation Required: {confirm1.requires_confirmation} | Prompts: {confirm1.confirmations_required}")
    assert confirm1.requires_confirmation is True
    assert len(confirm1.confirmations_required) == 1
    res1 = tool_execution_layer.execute_plan(plan1)
    print(f"Plan 1 Outcome: {res1.outcome.value} | Spoken: '{res1.spoken_summary}'")
    assert res1.outcome == ValidationOutcome.COMPLETE_SUCCESS

    print("\n--- Test 2: Multi-step chain with 2 distinct irreversible intents ---")
    plan2 = ExecutionPlan(
        plan_id="plan-live-2",
        request_id="req-live-102",
        steps=[
            ToolStep(step_id="s1", tool_name="file_system", action="delete_old_database", destructive=True),
            ToolStep(step_id="s2", tool_name="calendar_tool", action="purge_calendar_events", destructive=True),
        ],
    )
    confirm2 = TrustGate.evaluate_plan(plan2)
    print(f"Plan 2 Confirmation Required: {confirm2.requires_confirmation} | Prompts Count: {len(confirm2.confirmations_required)}")
    assert confirm2.requires_confirmation is True
    assert len(confirm2.confirmations_required) == 2

    print("\n--- Test 3: Cancelled Mid-Chain Execution ---")
    plan3 = ExecutionPlan(
        plan_id="plan-live-3",
        request_id="req-live-103",
        steps=[
            ToolStep(step_id="s1", tool_name="system_control", action="query_memory"),
            ToolStep(step_id="s2", tool_name="email_tool", action="send_broadcast", destructive=True),
        ],
    )
    tool_execution_layer.request_cancel("req-live-103")
    res3 = tool_execution_layer.execute_plan(plan3)
    print(f"Plan 3 Outcome: {res3.outcome.value} | Spoken: '{res3.spoken_summary}'")
    assert res3.outcome == ValidationOutcome.FATAL_FAILURE
    assert len(res3.step_results) == 1  # Aborted before step s1

    print("\n--- Test 4: Partial Failure Case Producing Audible Explanation ---")
    plan4 = ExecutionPlan(
        plan_id="plan-live-4",
        request_id="req-live-104",
        steps=[
            ToolStep(step_id="s1", tool_name="file_system", action="read_config"),
            ToolStep(step_id="s2", tool_name="email_tool", action="send_status_report"),
        ],
    )
    def fail_email(params):
        raise RuntimeError("SMTP Connection Failed")

    res4 = tool_execution_layer.execute_plan(plan4, executor_override={"s2": fail_email})
    print(f"Plan 4 Outcome: {res4.outcome.value} | Spoken: '{res4.spoken_summary}'")
    assert res4.outcome == ValidationOutcome.PARTIAL_SUCCESS
    assert "completed steps for file_system, but failed to complete email_tool" in res4.spoken_summary

    print("\n=" * 80)
    print("LIVE TOOL EXECUTION LAYER VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_live_tel_verification()
