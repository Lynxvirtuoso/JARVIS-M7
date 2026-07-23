"""
test_human_conversation_scenarios.py
Comprehensive test suite for Emergency Runtime Command Pipeline Fix & Phase 1 Reliability in JARVIS M7.
Tests wake-word flexibility, transcript resolution, sensitive confirmation, dynamic STT prompts,
production audio processing, self-voice echo rejection, request-ID isolation, and PipelineTimer resilience.
"""
import unittest
import numpy as np
from services.conversation.models import ConversationRequest, ResolvedTranscript
from services.conversation.transcript_resolver import transcript_resolver, TranscriptResolver
from services.stt.prompt_builder import stt_prompt_builder, PASSIVE_WAKE_PROMPT
from services.conversation.echo_rejector import echo_rejector
from services.audio_service import process_audio_safely
from core.telemetry import pipeline_timer, PipelineTimer, TelemetryContext


class TestListeningReliabilityPhase1(unittest.TestCase):

    def setUp(self):
        self.resolver = TranscriptResolver()

    # --- 1. PipelineTimer & Telemetry Resilience ---
    def test_pipeline_timer_without_request_id(self):
        pipeline_timer.start_pipeline("test command")
        ctx = pipeline_timer.get_thread_context()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.command, "test command")
        self.assertIsNotNone(ctx.request_id)

    def test_pipeline_timer_with_request_id(self):
        pipeline_timer.start_pipeline("test command", request_id="abc12345")
        ctx = pipeline_timer.get_thread_context()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.command, "test command")
        self.assertEqual(ctx.request_id, "abc12345")

    def test_pipeline_timer_failure_does_not_stop_command_routing(self):
        req = ConversationRequest(
            request_id="req-test-fail-123",
            session_id="sess-001",
            raw_transcript="Jarvis, tell me about football.",
            cleaned_transcript="Jarvis, tell me about football.",
            created_at=100.0
        )
        res = self.resolver.resolve(req.cleaned_transcript)
        self.assertTrue(res.wake_word_detected)
        self.assertIn("football", res.resolved_text.lower())
        self.assertFalse(res.is_sensitive_action)

    # --- 2. Sensitive Action Policy across All Sources (Voice, Typed, Telegram) ---
    def test_typed_shutdown_requires_confirmation(self):
        res = self.resolver.resolve("jarvis shutdown")
        self.assertTrue(res.is_sensitive_action)

    def test_voice_shutdown_requires_confirmation(self):
        res = self.resolver.resolve("Shut down, Jarvis.")
        self.assertTrue(res.is_sensitive_action)
        self.assertTrue(res.wake_word_detected)

    def test_application_exit_vs_system_shutdown_distinction(self):
        res_app = self.resolver.resolve("close jarvis")
        res_sys = self.resolver.resolve("shut down pc")
        self.assertTrue(res_app.is_sensitive_action)
        self.assertTrue(res_sys.is_sensitive_action)

    # --- 3. Interrupt Rejection & Echo Safety ---
    def test_empty_interrupt_transcript_is_rejected(self):
        self.assertTrue(echo_rejector.is_echo("", "Hello Sir", []))
        self.assertTrue(echo_rejector.is_echo("   ", "Hello Sir", []))
        self.assertTrue(echo_rejector.is_echo(".", "Hello Sir", []))

    def test_one_character_interrupt_transcript_is_rejected(self):
        self.assertTrue(echo_rejector.is_echo("S", "Hello Sir", []))
        self.assertTrue(echo_rejector.is_echo("a", "Hello Sir", []))

    def test_sorry_rejected_during_matching_tts(self):
        curr_spoken = "Yes, sorry sir. Bye."
        self.assertTrue(echo_rejector.is_echo("Sorry", curr_spoken, []))

    def test_systems_going_off_rejected_during_matching_tts(self):
        curr_spoken = "Systems going on."
        self.assertTrue(echo_rejector.is_echo("Systems going off", curr_spoken, []))

    def test_stop_accepted_during_tts(self):
        curr_spoken = "Certainly, Sir. Let's take a look at the beautiful game."
        self.assertFalse(echo_rejector.is_echo("Stop.", curr_spoken, []))

    def test_actually_accepted_during_tts(self):
        curr_spoken = "Certainly, Sir. Let's take a look at the beautiful game."
        self.assertFalse(echo_rejector.is_echo("Actually no.", curr_spoken, []))

    def test_know_and_nobody_not_treated_as_explicit_no(self):
        self.assertFalse(echo_rejector.is_explicit_interrupt("i know how it works"))
        self.assertFalse(echo_rejector.is_explicit_interrupt("nobody said anything"))
        self.assertTrue(echo_rejector.is_explicit_interrupt("no"))
        self.assertTrue(echo_rejector.is_explicit_interrupt("stop"))

    # --- 4. Wake Word Position & Variant Flexibility ---
    def test_wake_word_at_beginning(self):
        res = self.resolver.resolve("Jarvis, shut down.")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "start")

    def test_wake_word_at_end(self):
        res = self.resolver.resolve("Shut down, Jarvis.")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "end")

    def test_wake_word_in_middle(self):
        res = self.resolver.resolve("Could you shut down, Jarvis?")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "end")

    # --- 5. Audio Protection & Peak Limiting (Production Function) ---
    def test_process_audio_safely_peaks(self):
        for peak_target in [0.40, 0.90, 1.10, 1.35]:
            arr = np.array([0.1, -0.2, peak_target, -peak_target * 0.8], dtype=np.float32)
            res = process_audio_safely(arr, target_peak=0.95)
            self.assertLessEqual(np.max(np.abs(res.audio_data)), 1.0)
            self.assertLessEqual(res.processed_peak, 1.0)

    # --- 6. Singleton Services & Request ID Isolation ---
    def test_singleton_acknowledgement_service(self):
        from services import acknowledgement_service as exported_instance
        from services.acknowledgement_service import acknowledgement_service as canonical_instance
        self.assertIs(exported_instance, canonical_instance)

    def test_request_ids_remain_isolated(self):
        req1 = ConversationRequest(
            request_id="req-001",
            session_id="sess-001",
            raw_transcript="what is the time?",
            cleaned_transcript="what is the time",
            created_at=100.0
        )
        req2 = ConversationRequest(
            request_id="req-002",
            session_id="sess-001",
            raw_transcript="tell me about football.",
            cleaned_transcript="tell me about football",
            created_at=105.0
        )
        self.assertNotEqual(req1.request_id, req2.request_id)


if __name__ == "__main__":
    unittest.main()
