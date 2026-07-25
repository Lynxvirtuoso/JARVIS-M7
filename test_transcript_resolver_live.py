"""
LIVE TRANSCRIPT RESOLVER & DETERMINISTIC TIER VERIFICATION HARNESS
==================================================================
Tests:
1. "Jarvis what is the time now?" & "what's the time now please" -> Deterministic time resolution, no clarification.
2. "Jarvis, can you explain about football?", "what is the capital of France", "tell me about black holes" -> Conversational questions, no clarification even with low STT confidence/audio quality.
3. Genuinely garbled / low-confidence input -> still triggers needs_clarification.
"""

import sys
import os
import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

print("=" * 80)
print(f"LIVE TRANSCRIPT RESOLVER VERIFICATION STARTED AT {datetime.datetime.now().isoformat()}")
print("=" * 80)

from services.conversation.transcript_resolver import transcript_resolver

def run_live_verification():
    print("\n--- Test 1: Deterministic Time Tier Variants ---")
    time_queries = ["Jarvis what is the time now?", "what's the time now please", "Jarvis tell me the time currently"]
    for q in time_queries:
        res = transcript_resolver.resolve(q)
        print(f"Query: '{q}' -> Resolved: '{res.resolved_text}' | Conf: {res.confidence:.2f} | Clarify: {res.needs_clarification}")
        assert res.needs_clarification is False

    print("\n--- Test 2: Open-Ended Conversational Questions with Low STT Confidence ---")
    conv_queries = [
        "Jarvis, can you explain about football?",
        "what is the capital of France",
        "tell me about black holes"
    ]
    for q in conv_queries:
        # Simulate low STT confidence / audio quality (0.27)
        res = transcript_resolver.resolve(q, stt_confidence=0.27, audio_quality=1.0)
        print(f"Query: '{q}' -> Resolved: '{res.resolved_text}' | Conf: {res.confidence:.2f} | Clarify: {res.needs_clarification}")
        assert res.needs_clarification is False

    print("\n--- Test 3: Garbled / Non-Conversational Low-Confidence Input (True Positive Guard) ---")
    garbled_queries = ["xyz123 blarg flimflam", "open shmopen gorp"]
    for q in garbled_queries:
        res = transcript_resolver.resolve(q, stt_confidence=0.27, audio_quality=1.0)
        print(f"Query: '{q}' -> Resolved: '{res.resolved_text}' | Conf: {res.confidence:.2f} | Clarify: {res.needs_clarification}")
        assert res.needs_clarification is True

    print("\n=" * 80)
    print("LIVE TRANSCRIPT RESOLVER VERIFICATION PASSED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    run_live_verification()
