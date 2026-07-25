"""
LIVE SKILL ORCHESTRATOR VERIFICATION HARNESS
============================================
Verifies live SkillOrchestrator behavior across three representative scenarios:
1. Sequential: "check my calendar, then play my focus playlist"
2. Conditional: "if I'm free after 5pm, remind me to call John"
3. Data handoff: "find today's meeting notes and summarize them" (passes content via context)
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
print(f"LIVE SKILL ORCHESTRATOR VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from services.skills.orchestrator import skill_orchestrator
from services.tools.tool_execution_layer import tool_execution_layer
from services.tools.models import ValidationOutcome

def run_live_orchestrator_verification():
    print("\n--- Test 1: Sequential Scenario ---")
    cmd1 = "check my calendar, then play my focus playlist"
    plan1 = skill_orchestrator.plan_request("req-live-seq-1", cmd1)
    print(f"Plan 1 Created: ID={plan1.plan_id} | Steps Count={len(plan1.steps)}")
    print(f"Step 1: {plan1.steps[0].step_id} ({plan1.steps[0].tool_name})")
    print(f"Step 2: {plan1.steps[1].step_id} ({plan1.steps[1].tool_name}) -> depends_on: {plan1.steps[1].depends_on}")
    assert plan1.steps[1].depends_on == "step_1"
    res1 = tool_execution_layer.execute_plan(plan1)
    print(f"Plan 1 TEL Execution Outcome: {res1.outcome.value} | Spoken: '{res1.spoken_summary}'")
    assert res1.outcome == ValidationOutcome.COMPLETE_SUCCESS

    print("\n--- Test 1B: Sequential Scenario (Dependency Failure Skip Path) ---")
    plan1b = skill_orchestrator.plan_request("req-live-seq-1b", cmd1)
    def fail_calendar(params):
        raise RuntimeError("Calendar Service Offline")
    res1b = tool_execution_layer.execute_plan(plan1b, executor_override={"step_1": fail_calendar})
    print(f"Plan 1B TEL Outcome: {res1b.outcome.value} | Step 2 Skipped: {res1b.step_results[1].skipped} | Spoken: '{res1b.spoken_summary}'")
    assert res1b.outcome == ValidationOutcome.FATAL_FAILURE
    assert res1b.step_results[1].skipped is True
    assert res1b.step_results[1].skip_reason == "dependency_step_1_not_successful"
    assert "skipped because its dependency step_1 failed" in res1b.spoken_summary

    print("\n--- Test 2: Conditional Scenario (True condition) ---")
    cmd2 = "if I'm free after 5pm, remind me to call John"
    plan2 = skill_orchestrator.plan_request("req-live-cond-2", cmd2)
    plan2.context["is_free_after_1700"] = True
    print(f"Plan 2 Created: ID={plan2.plan_id} | Pattern={plan2.metadata['pattern']}")
    print(f"Step 2 Condition: {plan2.steps[1].condition} | depends_on: {plan2.steps[1].depends_on}")
    assert plan2.steps[1].depends_on == "step_1"
    assert plan2.steps[1].condition == "is_free_after_1700"
    res2 = tool_execution_layer.execute_plan(plan2)
    print(f"Plan 2 TEL Execution Outcome: {res2.outcome.value}")
    assert res2.outcome == ValidationOutcome.COMPLETE_SUCCESS

    print("\n--- Test 2B: Conditional Scenario (False condition skip path) ---")
    plan2b = skill_orchestrator.plan_request("req-live-cond-2b", cmd2)
    plan2b.context["is_free_after_1700"] = False
    res2b = tool_execution_layer.execute_plan(plan2b)
    print(f"Plan 2B TEL Outcome: {res2b.outcome.value} | Step 2 Skipped: {res2b.step_results[1].skipped} | Spoken: '{res2b.spoken_summary}'")
    assert res2b.outcome == ValidationOutcome.COMPLETE_SUCCESS
    assert res2b.step_results[1].skipped is True
    assert "not free after 5 PM" in res2b.spoken_summary

    print("\n--- Test 3: Data Handoff Scenario ---")
    cmd3 = "find today's meeting notes and summarize them"
    plan3 = skill_orchestrator.plan_request("req-live-handoff-3", cmd3)
    print(f"Plan 3 Initial Context: {plan3.context}")

    # Simulate Step 1 populating context for Step 2
    def file_finder_step1(params):
        content = "Meeting Notes (2026-07-25): Discussed Phase 2.4 Skill Orchestration architecture."
        plan3.context["meeting_notes_content"] = content
        return f"Found file with content ({len(content)} chars)"

    def llm_summarizer_step2(params):
        key = params.get("input_context_key")
        content = plan3.context.get(key, "")
        return f"Summary: {content}"

    res3 = tool_execution_layer.execute_plan(
        plan3,
        executor_override={"step_1": file_finder_step1, "step_2": llm_summarizer_step2},
    )
    print(f"Plan 3 Final Handoff Context: '{plan3.context['meeting_notes_content']}'")
    print(f"Step 2 Summary Output: '{res3.step_results[1].output}'")
    assert "Discussed Phase 2.4" in plan3.context["meeting_notes_content"]
    assert res3.outcome == ValidationOutcome.COMPLETE_SUCCESS

    print("\n=" * 80)
    print("LIVE SKILL ORCHESTRATOR VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_live_orchestrator_verification()
