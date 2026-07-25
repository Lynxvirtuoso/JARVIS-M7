"""
latency_budget_report.py
Offline aggregator and reporting utility for Phase 2.7.1 Latency Profiling.
Parses telemetry log files / events to produce per-agent stage latency budgets (min/median/p95).
"""

import sys
import os
import re
import statistics
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def calc_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    min_v = sorted_vals[0]
    med_v = statistics.median(sorted_vals)
    p95_idx = int(0.95 * (len(sorted_vals) - 1))
    p95_v = sorted_vals[p95_idx]
    return {"min": min_v, "median": med_v, "p95": p95_v}


class LatencyBudgetReport:

    @staticmethod
    def parse_log_file(log_path: str) -> Dict[str, Dict[str, List[float]]]:
        """
        Parses log file for agent stage telemetry events and computes marker intervals:
        network_and_queue_time = first_token_received ts - provider_request_sent ts
        streaming_time = last_token_received ts - first_token_received ts
        """
        data: Dict[str, Dict[str, List[float]]] = {}

        if not os.path.exists(log_path):
            print(f"Log file not found: {log_path}")
            return data

        content = ""
        for enc in ["utf-8", "utf-16le", "utf-16", "cp1252"]:
            try:
                with open(log_path, "r", encoding=enc) as f:
                    content = f.read()
                if "agent_stage" in content or "[TELEMETRY_LATENCY]" in content:
                    break
            except Exception:
                continue

        lines = content.splitlines()

        # 1. Parse standard agent_stage events
        pattern = re.compile(r"agent_stage:([^:]+):([^:]+):([^:]+):([^:]+):([0-9\.]+)ms(?::ts=([0-9\.]+))?")
        
        # Track timestamps per (request_id, step_id, role, marker)
        markers: Dict[str, Dict[str, float]] = {}

        for line in lines:
            match = pattern.search(line)
            if match:
                req_id, step_id, role, stage, dur_str, ts_str = match.groups()
                dur_ms = float(dur_str)
                
                # Filter out pure point markers (0.00ms) from standard stage duration list
                if not (stage in ("provider_request_sent", "first_token_received", "last_token_received") and dur_ms == 0.0):
                    if role not in data:
                        data[role] = {}
                    if stage not in data[role]:
                        data[role][stage] = []
                    data[role][stage].append(dur_ms)

                # Store marker timestamp if present
                if ts_str:
                    key = f"{req_id}:{step_id}:{role}"
                    if key not in markers:
                        markers[key] = {}
                    markers[key][stage] = float(ts_str)

        # 2. Extract marker timestamps from log line timestamps or TELEMETRY_LATENCY events
        log_ts_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}).* agent_stage:([^:]+):([^:]+):([^:]+):([^:]+):")
        telemetry_latency_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}).*\[TELEMETRY_LATENCY\]\s+(.*)")
        step_event_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}).*\[TELEMETRY\].*Event:\s+agent_step_(start|end):(\w+)")

        current_role = None
        current_req = "req-live-25b-001"
        current_step = None

        for line in lines:
            # Match explicit agent_stage events
            m_stage = log_ts_pattern.search(line)
            if m_stage:
                time_str, req_id, step_id, role, stage = m_stage.groups()
                try:
                    import datetime
                    dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
                    epoch_ts = dt.timestamp()
                    key = f"{req_id}:{step_id}:{role}"
                    if key not in markers:
                        markers[key] = {}
                    if stage not in markers[key]:
                        markers[key][stage] = epoch_ts
                except Exception:
                    pass
                continue

            # Match step start / step end
            m_step = step_event_pattern.search(line)
            if m_step:
                time_str, action, role = m_step.groups()
                current_role = role
                current_step = f"step_{role.lower()}"
                try:
                    import datetime
                    dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
                    epoch_ts = dt.timestamp()
                    key = f"{current_req}:{current_step}:{role}"
                    if key not in markers:
                        markers[key] = {}
                except Exception:
                    pass
                continue

            # Match TELEMETRY_LATENCY logs when agent_stage events are absent
            m_lat = telemetry_latency_pattern.search(line)
            if m_lat and current_role and current_step:
                time_str, msg = m_lat.groups()
                try:
                    import datetime
                    dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
                    epoch_ts = dt.timestamp()
                    key = f"{current_req}:{current_step}:{current_role}"
                    if key not in markers:
                        markers[key] = {}

                    if "Outbound Groq request sending" in msg or "Attempting provider" in msg:
                        if "provider_request_sent" not in markers[key]:
                            markers[key]["provider_request_sent"] = epoch_ts
                    elif "first token yielded" in msg or "Groq HTTP response status" in msg:
                        if "first_token_received" not in markers[key]:
                            markers[key]["first_token_received"] = epoch_ts
                except Exception:
                    pass

        # 3. Compute marker intervals per agent step
        for key, m_dict in markers.items():
            role = key.split(":")[2]
            if role not in data:
                data[role] = {}

            req_sent = m_dict.get("provider_request_sent")
            first_tok = m_dict.get("first_token_received")
            last_tok = m_dict.get("last_token_received") or m_dict.get("first_token_received")

            if req_sent and first_tok and first_tok >= req_sent:
                net_dur = (first_tok - req_sent) * 1000.0
                if "network_and_queue_time" not in data[role]:
                    data[role]["network_and_queue_time"] = []
                data[role]["network_and_queue_time"].append(net_dur)

            if first_tok and last_tok and last_tok >= first_tok:
                stream_dur = (last_tok - first_tok) * 1000.0
                if "streaming_time" not in data[role]:
                    data[role]["streaming_time"] = []
                data[role]["streaming_time"].append(stream_dur)

        return data

    @classmethod
    def generate_report(cls, log_path: str):
        data = cls.parse_log_file(log_path)

        print("=" * 80)
        print(f"LATENCY BUDGET REPORT (Source: {os.path.basename(log_path)})")
        print("=" * 80)

        if not data:
            print("No structured stage telemetry events found in log file.")
            print("=" * 80)
            return

        roles_order = ["Planner", "Research", "Tool", "Critic", "Synthesizer"]
        
        for role in roles_order:
            if role not in data:
                continue
            stages = data[role]
            print(f"\n[AGENT ROLE: {role}]")
            print("-" * 75)
            print(f"{'Stage Name':<28} | {'Min (ms)':<10} | {'Median (ms)':<12} | {'P95 (ms)':<10}")
            print("-" * 75)
            
            for stage_name, durations in stages.items():
                stats = calc_stats(durations)
                print(f"{stage_name:<28} | {stats['min']:<10.2f} | {stats['median']:<12.2f} | {stats['p95']:<10.2f}")
            print("-" * 75)

        print("=" * 80)


if __name__ == "__main__":
    target_log = sys.argv[1] if len(sys.argv) > 1 else "phase2_7_1_live.log"
    LatencyBudgetReport.generate_report(target_log)
