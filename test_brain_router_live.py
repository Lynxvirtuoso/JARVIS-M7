"""
LIVE BRAIN ROUTER VERIFICATION HARNESS
======================================
Verifies that BrainRouter cleanly sets starting provider tier in live ProviderManager calls:
1. is_private=True starts at 'ollama'
2. is_private=False starts at 'groq'
3. Provider failure at starting tier cleanly falls through unchanged.
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
print(f"LIVE BRAIN ROUTER VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from services.brain.provider_manager import brain_manager, BrainRequest, BrainResult
from services.brain.router import brain_router

def run_live_brain_router_harness():
    print("\n--- Test 1: Default Mode (is_private=False) ---")
    req_default = BrainRequest(text="Explain gravity in simple terms", is_private=False)
    route, chain, web_needed = brain_manager.determine_route(req_default)
    print(f"Default Starting Chain: {chain} | First Tier: {chain[0]}")
    assert chain[0] == "groq"

    print("\n--- Test 2: Privacy Mode (is_private=True) ---")
    req_private = BrainRequest(text="Summarize my local tax documents", is_private=True)
    route, chain_p, web_needed_p = brain_manager.determine_route(req_private)
    print(f"Privacy Mode Starting Chain: {chain_p} | First Tier: {chain_p[0]}")
    assert chain_p[0] == "ollama"

    print("\n--- Test 3: Fallthrough Integrity on Provider Failure ---")
    # Backup original groq think method and inject failure
    groq_provider = brain_manager.providers.get("groq")
    if groq_provider:
        orig_think = groq_provider.think
        def failing_think(*args, **kwargs):
            raise RuntimeError("Simulated Groq Failure")
        groq_provider.think = failing_think

        try:
            res = brain_manager.think(req_default)
            print(f"Fallback Provider Selected: {res.provider} | Success: {res.success}")
            assert res.provider != "groq"
            assert res.success is True
        finally:
            groq_provider.think = orig_think

    print("\n=" * 80)
    print("LIVE BRAIN ROUTER VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_live_brain_router_harness()
