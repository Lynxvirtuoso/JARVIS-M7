"""
test_phase2_5c_benchmark_clean.py
Phase 2.5c Performance Benchmarking Harness for JARVIS M7 (Clean Provider Run).
Measures wall-clock latency and per-agent-role latency across 3 scenarios (N=15 runs each).
"""

import sys
import os
import time
import statistics
import datetime
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from services.agents.coordinator import agent_coordinator
from services.brain.router import brain_router
from core.telemetry import pipeline_timer
from services.groq_quota_manager import groq_quota_manager
from core.database import db


def calc_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"median": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    med = statistics.median(sorted_vals)
    p95_idx = int(0.95 * (len(sorted_vals) - 1))
    p95 = sorted_vals[p95_idx]
    return {"median": med, "p95": p95}


def run_benchmarks(num_runs: int = 15):
    print("=" * 80)
    print(f"PHASE 2.5c BENCHMARKING HARNESS (N={num_runs} runs per scenario)")
    print(f"Started at: {datetime.datetime.now().isoformat()}")
    print("=" * 80)

    # Scenario 1: Simple single-agent query (Deterministic tier)
    print(f"\nRunning Scenario 1 (single-agent, deterministic) {num_runs} times...")
    s1_latencies = []
    s1_routes = []
    for i in range(num_runs):
        start_t = time.time()
        dec = brain_router.route("what time is it")
        elapsed = (time.time() - start_t) * 1000.0
        s1_latencies.append(elapsed)
        s1_routes.append(dec.route)

    # Scenario 2: Single tool call / action intent
    print(f"Running Scenario 2 (single-agent, tool call) {num_runs} times...")
    s2_latencies = []
    s2_routes = []
    for i in range(num_runs):
        start_t = time.time()
        dec = brain_router.route("open calculator")
        elapsed = (time.time() - start_t) * 1000.0
        s2_latencies.append(elapsed)
        s2_routes.append(dec.route)

    # Scenario 3: Full multi-agent chain
    cmd_multi = "check my calendar and remind me to call John if I'm free"
    print(f"Running Scenario 3 (multi-agent, full chain) {num_runs} times...")
    s3_total_latencies = []
    s3_routes = []
    role_latencies: Dict[str, List[float]] = {
        "Planner": [],
        "Research": [],
        "Tool": [],
        "Critic": [],
        "Synthesizer": []
    }

    for i in range(num_runs):
        req_id = f"req-bench-clean-{i+1:03d}"
        
        # Clear any artificial cooldown state before each run to avoid 429 quota fallback artifacts
        groq_quota_manager.cooldowns.clear()
        
        dec = brain_router.route(cmd_multi)
        s3_routes.append(dec.route)

        start_t = time.time()
        role_start_times: Dict[str, float] = {}

        def timer_hook(event_name: str):
            if event_name.startswith("agent_step_start:"):
                role = event_name.split(":")[1]
                role_start_times[role] = time.time()
            elif event_name.startswith("agent_step_end:"):
                role = event_name.split(":")[1]
                if role in role_start_times:
                    dur = (time.time() - role_start_times[role]) * 1000.0
                    role_latencies[role].append(dur)

        original_log_event = pipeline_timer.log_event
        def intercept_log_event(name: str):
            original_log_event(name)
            timer_hook(name)

        pipeline_timer.log_event = intercept_log_event

        res = agent_coordinator.run(req_id, cmd_multi)
        elapsed = (time.time() - start_t) * 1000.0
        s3_total_latencies.append(elapsed)

        pipeline_timer.log_event = original_log_event
        time.sleep(1.0)  # Gentle 1s pacing between network API calls

    # Statistics computation
    s1_stats = calc_stats(s1_latencies)
    s2_stats = calc_stats(s2_latencies)
    s3_stats = calc_stats(s3_total_latencies)

    role_stats = {role: calc_stats(lat_list) for role, lat_list in role_latencies.items()}

    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS TABLE")
    print("=" * 80)
    print(f"Scenario 1 (single-agent, deterministic): N={num_runs} | Median: {s1_stats['median']:.2f}ms | P95: {s1_stats['p95']:.2f}ms | Routes: {set(s1_routes)}")
    print(f"Scenario 2 (single-agent, tool call):      N={num_runs} | Median: {s2_stats['median']:.2f}ms | P95: {s2_stats['p95']:.2f}ms | Routes: {set(s2_routes)}")
    print(f"Scenario 3 (multi-agent, full chain):      N={num_runs} | Median: {s3_stats['median']:.2f}ms | P95: {s3_stats['p95']:.2f}ms | Routes: {set(s3_routes)}")
    print(f"  ├── Planner:     Median: {role_stats['Planner']['median']:.2f}ms | P95: {role_stats['Planner']['p95']:.2f}ms")
    print(f"  ├── Research:    Median: {role_stats['Research']['median']:.2f}ms | P95: {role_stats['Research']['p95']:.2f}ms")
    print(f"  ├── Tool:        Median: {role_stats['Tool']['median']:.2f}ms | P95: {role_stats['Tool']['p95']:.2f}ms")
    print(f"  ├── Critic:      Median: {role_stats['Critic']['median']:.2f}ms | P95: {role_stats['Critic']['p95']:.2f}ms")
    print(f"  └── Synthesizer: Median: {role_stats['Synthesizer']['median']:.2f}ms | P95: {role_stats['Synthesizer']['p95']:.2f}ms")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmarks(num_runs=15)
