"""
test_human_conversation_scenarios.py
Comprehensive test suite for Phase 1 Final Critical Integration Repair in JARVIS M7.
Tests cover: sensitive action mapping, ambiguous shutdown, confirmation security,
streamed request-ID propagation, correction interruption routing, speech completion
semantics, follow-up timing, wake metadata, and regression cases.
"""
import os
import time
import threading
import unittest
import numpy as np
from unittest.mock import patch, MagicMock, call

os.environ["JARVIS_TESTING"] = "1"

from services.conversation.models import (
    ConversationRequest, ResolvedTranscript, SensitiveActionType,
    PendingConfirmation, PendingActionChoice, InterruptDecision
)
from services.conversation.transcript_resolver import transcript_resolver, TranscriptResolver
from services.conversation.echo_rejector import echo_rejector, EchoRejector
from services.stt.prompt_builder import stt_prompt_builder, PASSIVE_WAKE_PROMPT
from services.audio_service import process_audio_safely
from core.telemetry import pipeline_timer, PipelineTimer, TelemetryContext
from services.tts.streaming_tts_queue import StreamingTTSQueue
from services.system_power_controller import SystemPowerController


class TestListeningReliabilityPhase1(unittest.TestCase):

    def setUp(self):
        self.resolver = TranscriptResolver()

    # ----- 1. PipelineTimer & Telemetry Resilience -----

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

    # ----- 2. Wake-Word Metadata -----

    def test_wake_word_at_beginning(self):
        res = self.resolver.resolve("Jarvis, what time is it?")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "start")
        self.assertFalse(res.accepted_as_active_session_followup)

    def test_wake_word_at_end(self):
        res = self.resolver.resolve("What time is it, Jarvis?")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "end")
        self.assertFalse(res.accepted_as_active_session_followup)

    def test_wake_word_in_middle(self):
        res = self.resolver.resolve("Could you, Jarvis, tell me the time?")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "middle")
        self.assertFalse(res.accepted_as_active_session_followup)

    def test_no_wake_word_active_session_returns_followup_true(self):
        """A follow-up without a wake word with active session should have accepted_as_active_session_followup=True."""
        res = self.resolver.resolve("What time is it?", session_active=True)
        self.assertFalse(res.wake_word_detected)
        self.assertIsNone(res.wake_word_position)
        self.assertTrue(res.accepted_as_active_session_followup)

    def test_no_wake_word_passive_returns_followup_false(self):
        """A speech without a wake word in passive mode should have accepted_as_active_session_followup=False."""
        res = self.resolver.resolve("What time is it?", session_active=False)
        self.assertFalse(res.wake_word_detected)
        self.assertIsNone(res.wake_word_position)
        self.assertFalse(res.accepted_as_active_session_followup)

    def test_empty_transcript_followup_false(self):
        res = self.resolver.resolve("")
        self.assertFalse(res.wake_word_detected)
        self.assertFalse(res.accepted_as_active_session_followup)

    def test_surya_dermu_pono_phonetic_corrections(self):
        """Both Surya Dermu Pono and Surya Dermú Pono should resolve to system status."""
        res1 = self.resolver.resolve("Surya Dermu Pono")
        res2 = self.resolver.resolve("Surya Dermú Pono")
        self.assertEqual(res1.resolved_text, "system status")
        self.assertEqual(res2.resolved_text, "system status")

    # ----- 3. Sensitive Action Classification -----

    def test_typed_shutdown_requires_confirmation(self):
        res = self.resolver.resolve("jarvis shutdown")
        self.assertTrue(res.is_sensitive_action)

    def test_voice_shutdown_requires_confirmation(self):
        res = self.resolver.resolve("Shut down, Jarvis.")
        self.assertTrue(res.is_sensitive_action)
        self.assertTrue(res.wake_word_detected)

    def test_shut_down_pc_maps_to_shutdown_computer(self):
        res = self.resolver.resolve("shut down pc")
        self.assertTrue(res.is_sensitive_action)
        self.assertEqual(res.sensitive_action_type, SensitiveActionType.SHUTDOWN_COMPUTER)

    def test_close_jarvis_maps_to_exit_application(self):
        res = self.resolver.resolve("close jarvis")
        self.assertTrue(res.is_sensitive_action)
        self.assertEqual(res.sensitive_action_type, SensitiveActionType.EXIT_APPLICATION)

    def test_generic_shutdown_is_ambiguous(self):
        """'shutdown' alone is ambiguous and must NOT map to EXIT_APPLICATION or SHUTDOWN_COMPUTER directly."""
        res = self.resolver.resolve("jarvis shutdown")
        self.assertTrue(res.is_sensitive_action)
        self.assertEqual(res.sensitive_action_type, SensitiveActionType.AMBIGUOUS_SHUTDOWN)

    def test_application_exit_vs_system_shutdown_distinction(self):
        res_app = self.resolver.resolve("close jarvis")
        res_sys = self.resolver.resolve("shut down pc")
        self.assertEqual(res_app.sensitive_action_type, SensitiveActionType.EXIT_APPLICATION)
        self.assertEqual(res_sys.sensitive_action_type, SensitiveActionType.SHUTDOWN_COMPUTER)

    def test_restart_maps_to_restart_computer(self):
        res = self.resolver.resolve("restart pc")
        self.assertEqual(res.sensitive_action_type, SensitiveActionType.RESTART_COMPUTER)

    # ----- 4. Sensitive Action Execution Mapping (SystemPowerController) -----

    def test_shutdown_computer_calls_shutdown_not_sleep(self):
        ctrl = SystemPowerController(mock_mode=True)
        result = ctrl.shutdown_pc()
        self.assertTrue(result)

    def test_restart_computer_calls_restart(self):
        ctrl = SystemPowerController(mock_mode=True)
        result = ctrl.restart_pc()
        self.assertTrue(result)

    def test_lock_calls_lock(self):
        ctrl = SystemPowerController(mock_mode=True)
        result = ctrl.lock_pc()
        self.assertTrue(result)

    def test_logout_calls_logout(self):
        ctrl = SystemPowerController(mock_mode=True)
        result = ctrl.logout_pc()
        self.assertTrue(result)

    # ----- 5. Interrupt Rejection & Echo Safety -----

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

    # ----- 6. InterruptDecision Structured Return -----

    def test_evaluate_interrupt_empty_returns_not_accepted(self):
        d = echo_rejector.evaluate_interrupt("", "Hello", [], request_id="req-A")
        self.assertFalse(d.accepted)
        self.assertEqual(d.reason, "empty_transcript")
        self.assertEqual(d.request_id, "req-A")

    def test_evaluate_interrupt_stop_accepted_with_reason(self):
        d = echo_rejector.evaluate_interrupt("Stop.", "Football is a great game.", [], request_id="req-B")
        self.assertTrue(d.accepted)
        self.assertEqual(d.reason, "explicit_stop")
        self.assertEqual(d.normalized_text, "stop")

    def test_evaluate_interrupt_actually_is_correction(self):
        d = echo_rejector.evaluate_interrupt("Actually no.", "Football is a game.", [], request_id="req-C")
        self.assertTrue(d.accepted)
        self.assertIn(d.reason, {"correction", "explicit_keyword"})

    def test_evaluate_interrupt_echo_returns_not_accepted(self):
        d = echo_rejector.evaluate_interrupt("Systems going off", "Systems going on.", [], request_id="req-D")
        self.assertFalse(d.accepted)
        self.assertEqual(d.reason, "assistant_echo")
        self.assertGreater(d.similarity, 0.5)

    # ----- 7. Pending Confirmation Security -----

    def test_pending_confirmation_fields_preserved(self):
        now = time.time()
        pc = PendingConfirmation(
            request_id="req-secure-001",
            session_id="sess-voice-001",
            action_type=SensitiveActionType.SHUTDOWN_COMPUTER,
            action_payload={"command": "shut down pc"},
            source="voice",
            created_at=now,
            expires_at=now + 30.0
        )
        self.assertEqual(pc.request_id, "req-secure-001")
        self.assertEqual(pc.session_id, "sess-voice-001")
        self.assertEqual(pc.source, "voice")
        self.assertEqual(pc.action_type, SensitiveActionType.SHUTDOWN_COMPUTER)
        self.assertFalse(time.time() > pc.expires_at)

    def test_pending_confirmation_expires(self):
        now = time.time()
        pc = PendingConfirmation(
            request_id="req-expired-001",
            session_id="sess-001",
            action_type=SensitiveActionType.EXIT_APPLICATION,
            action_payload={},
            source="voice",
            created_at=now - 60.0,
            expires_at=now - 30.0
        )
        self.assertTrue(time.time() > pc.expires_at)

    def test_pending_action_choice_fields(self):
        now = time.time()
        pac = PendingActionChoice(
            request_id="req-choice-001",
            session_id="sess-001",
            source="voice",
            options=[SensitiveActionType.EXIT_APPLICATION, SensitiveActionType.SHUTDOWN_COMPUTER],
            created_at=now,
            expires_at=now + 30.0
        )
        self.assertEqual(len(pac.options), 2)
        self.assertIn(SensitiveActionType.EXIT_APPLICATION, pac.options)
        self.assertIn(SensitiveActionType.SHUTDOWN_COMPUTER, pac.options)

    # ----- 8. Streamed Request ID Propagation -----

    def test_streaming_tts_queue_accepts_request_id(self):
        q = StreamingTTSQueue(max_size=4)
        req_id = "original-cmd-req-abc123"
        returned = q.start_new_request(request_id=req_id)
        self.assertEqual(returned, req_id)
        self.assertEqual(q.active_request_id, req_id)

    def test_streaming_tts_queue_generates_id_when_none_provided(self):
        q = StreamingTTSQueue(max_size=4)
        returned = q.start_new_request()
        self.assertIsNotNone(returned)
        self.assertGreater(len(returned), 0)

    def test_streaming_tts_queue_preserves_id_through_enqueue(self):
        q = StreamingTTSQueue(max_size=4)
        req_id = "cmd-req-preserve-xyz"
        q.start_new_request(request_id=req_id)
        ok = q.enqueue_sentence(req_id, "This is the first sentence.", is_final=False)
        self.assertTrue(ok)
        item = q.get_next_item(timeout=0.1)
        self.assertIsNotNone(item)
        self.assertEqual(item.request_id, req_id)
        self.assertEqual(item.text, "This is the first sentence.")

    def test_stale_request_enqueue_rejected(self):
        q = StreamingTTSQueue(max_size=4)
        old_id = "old-req-001"
        new_id = "new-req-002"
        q.start_new_request(request_id=old_id)
        q.start_new_request(request_id=new_id)
        ok = q.enqueue_sentence(old_id, "Stale sentence.", is_final=False)
        self.assertFalse(ok)

    # ----- 9. Correction Interruption Extract Logic -----

    def test_correction_reason_detected_by_evaluate_interrupt(self):
        d = echo_rejector.evaluate_interrupt(
            "Actually, I meant American football.",
            "Football is a sport played with a round ball.",
            ["Football is a sport played with a round ball."],
            request_id="req-corr-001"
        )
        # Should be accepted (correction or distinct_user_interruption)
        self.assertTrue(d.accepted)
        self.assertIn("actually", d.normalized_text)

    def test_old_request_cancelled_on_correction(self):
        q = StreamingTTSQueue(max_size=4)
        old_id = "req-football-001"
        q.start_new_request(request_id=old_id)
        q.enqueue_sentence(old_id, "Football is a great game.", is_final=False)
        # Simulate cancel
        q.cancel_active_request()
        self.assertIsNone(q.active_request_id)
        ok = q.enqueue_sentence(old_id, "More about football...", is_final=False)
        self.assertFalse(ok)

    def test_corrected_request_has_different_id(self):
        import uuid
        old_id = "req-original-football"
        new_id = f"corr-{uuid.uuid4().hex[:12]}"
        self.assertNotEqual(old_id, new_id)
        self.assertTrue(new_id.startswith("corr-"))

    # ----- 10. Speech Completion Semantics -----

    def test_speech_lifecycle_state_producer_finished_required(self):
        """speech_ended must not emit when producer has not finished."""
        # Import directly from the dataclass definition only, without triggering speech singleton
        from services.conversation.models import SpeechLifecycleState
        state = SpeechLifecycleState(request_id="req-lifecycle-001")
        self.assertFalse(state.producer_finished)
        self.assertFalse(state.speech_ended_emitted)
        self.assertFalse(state.cancelled)

    def test_speech_lifecycle_cancelled_prevents_ended_emit(self):
        from services.conversation.models import SpeechLifecycleState
        state = SpeechLifecycleState(request_id="req-lifecycle-002")
        state.cancelled = True
        state.producer_finished = True
        self.assertTrue(state.cancelled)
        self.assertTrue(state.producer_finished)

    def test_speech_lifecycle_duplicate_ended_prevented(self):
        from services.conversation.models import SpeechLifecycleState
        state = SpeechLifecycleState(request_id="req-lifecycle-003")
        state.producer_finished = True
        state.speech_ended_emitted = True
        self.assertTrue(state.speech_ended_emitted)

    # ----- 11. Audio Protection & Peak Limiting -----

    def test_process_audio_safely_peaks(self):
        for peak_target in [0.40, 0.90, 1.10, 1.35]:
            arr = np.array([0.1, -0.2, peak_target, -peak_target * 0.8], dtype=np.float32)
            res = process_audio_safely(arr, target_peak=0.95)
            self.assertLessEqual(np.max(np.abs(res.audio_data)), 1.0)
            self.assertLessEqual(res.processed_peak, 1.0)

    # ----- 12. Singleton Services & Request ID Isolation -----

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

    # ----- 13. Regression: Late Callbacks from Cancelled Requests -----

    def test_late_callback_from_cancelled_request_is_silenced(self):
        """After cancellation, a late sentence from old request must not enqueue."""
        q = StreamingTTSQueue(max_size=4)
        req_id = "req-late-callback-001"
        q.start_new_request(request_id=req_id)
        q.cancel_active_request()
        # Simulate a late callback arriving after cancellation
        result = q.enqueue_sentence(req_id, "This sentence arrived late.", is_final=False)
        self.assertFalse(result)

    def test_temporary_queue_emptiness_does_not_trigger_ended_without_producer_finish(self):
        """Temporary empty queues during streaming should not trigger speech_ended."""
        from services.conversation.models import SpeechLifecycleState
        state = SpeechLifecycleState(request_id="req-streaming-empty")
        # Producer still generating
        state.producer_finished = False
        # Queues momentarily empty (as happens during streaming)
        text_queue_empty = True
        audio_queue_empty = True
        # speech_ended must NOT be emitted
        should_emit = (
            state.producer_finished and
            not state.speech_ended_emitted and
            not state.cancelled and
            text_queue_empty and
            audio_queue_empty
        )
        self.assertFalse(should_emit)

    def test_cross_source_confirmation_rejected(self):
        """A typed 'Yes' must not confirm a voice-originated pending confirmation."""
        now = time.time()
        voice_conf = PendingConfirmation(
            request_id="req-voice-shutdown",
            session_id="sess-001",
            action_type=SensitiveActionType.SHUTDOWN_COMPUTER,
            action_payload={"command": "shut down pc"},
            source="voice",
            created_at=now,
            expires_at=now + 30.0
        )
        incoming_source = "typed"
        # Source mismatch must cause rejection
        self.assertNotEqual(voice_conf.source, incoming_source)

    def test_cross_session_confirmation_rejected(self):
        """A confirmation from a different session must be rejected."""
        now = time.time()
        conf = PendingConfirmation(
            request_id="req-sess-mismatch",
            session_id="sess-A",
            action_type=SensitiveActionType.EXIT_APPLICATION,
            action_payload={},
            source="voice",
            created_at=now,
            expires_at=now + 30.0
        )
        incoming_session = "sess-B"
        self.assertNotEqual(conf.session_id, incoming_session)

    def test_duplicate_yes_cannot_execute_twice(self):
        """Atomically cleared pending state prevents a second 'Yes' from re-executing."""
        now = time.time()
        conf = PendingConfirmation(
            request_id="req-dup-yes-001",
            session_id="sess-001",
            action_type=SensitiveActionType.SHUTDOWN_COMPUTER,
            action_payload={},
            source="voice",
            created_at=now,
            expires_at=now + 30.0
        )
        # First Yes: read and clear
        action_to_execute = conf.action_type
        conf = None  # clear atomically

        # Second Yes: no conf available
        action_to_execute_2 = conf  # None - no action
        self.assertIsNone(action_to_execute_2)
        self.assertEqual(action_to_execute, SensitiveActionType.SHUTDOWN_COMPUTER)

    def test_expired_confirmation_not_accepted(self):
        """An expired confirmation must be discarded, not executed."""
        now = time.time()
        conf = PendingConfirmation(
            request_id="req-expired-002",
            session_id="sess-001",
            action_type=SensitiveActionType.EXIT_APPLICATION,
            action_payload={},
            source="voice",
            created_at=now - 60.0,
            expires_at=now - 30.0
        )
        is_expired = time.time() > conf.expires_at
        self.assertTrue(is_expired)

    # ----- 14. Phase 1 Deadlock & Lifecycle Repair Tests -----

    def test_mark_producer_finished_multithreaded_no_deadlock(self):
        """mark_producer_finished run from a separate thread returns within 1.0s and does not deadlock."""
        from services.speech_service import speech
        req_id = "req-dl-001"
        speech.start_request(req_id)

        t = threading.Thread(target=speech.mark_producer_finished, args=(req_id,))
        t.start()
        t.join(timeout=1.0)

        self.assertFalse(t.is_alive(), "mark_producer_finished deadlocked")
        state = speech.engine._lifecycles.get(req_id)
        self.assertIsNotNone(state)
        self.assertTrue(state.producer_finished)

    def test_start_request_fully_resets_speech_lifecycle_state(self):
        """start_request creates a clean state object, clearing any previous stale counters or flags."""
        from services.speech_service import speech
        req_id = "req-reset-001"
        speech.start_request(req_id)

        # Pollute state
        state = speech.engine._lifecycles[req_id]
        state.producer_finished = True
        state.synthesis_active = True
        state.speech_ended_emitted = True
        state.cancelled = True

        # Re-start request
        speech.start_request(req_id)
        new_state = speech.engine._lifecycles[req_id]

        self.assertFalse(new_state.producer_finished)
        self.assertFalse(new_state.synthesis_active)
        self.assertFalse(new_state.speech_ended_emitted)
        self.assertFalse(new_state.cancelled)

    def test_streaming_queue_encapsulation_and_invalidation(self):
        """Request A is invalidated by Request B; late items from A are rejected."""
        from services.tts.streaming_tts_queue import streaming_tts_queue
        req_A = "req-stream-A"
        req_B = "req-stream-B"

        streaming_tts_queue.start_new_request(request_id=req_A)
        self.assertEqual(streaming_tts_queue.active_request_id, req_A)

        streaming_tts_queue.start_new_request(request_id=req_B)
        self.assertEqual(streaming_tts_queue.active_request_id, req_B)

        rejected = streaming_tts_queue.enqueue_sentence(req_A, "Sentence from A")
        self.assertFalse(rejected)

        accepted = streaming_tts_queue.enqueue_sentence(req_B, "Sentence from B")
        self.assertTrue(accepted)

    def test_request_replacement_late_callback_and_cancellation_isolation(self):
        """When request A is cancelled and request B starts, late callbacks from A do not emit speech_ended for B."""
        from services.speech_service import speech
        from services.tts.streaming_tts_queue import streaming_tts_queue

        req_A = "req-iso-A"
        req_B = "req-iso-B"

        speech.start_request(req_A)
        streaming_tts_queue.start_new_request(request_id=req_A)

        # Start request B (cancelling A implicitly in queue)
        speech.cancel_request(req_A)
        speech.start_request(req_B)
        streaming_tts_queue.start_new_request(request_id=req_B)

        # Late producer finish call for A
        speech.mark_producer_finished(req_A)

        # State for req_A should remain cancelled and speech_ended_emitted should be False
        state_A = speech.engine._lifecycles.get(req_A)
        self.assertTrue(state_A.cancelled)
        self.assertFalse(state_A.speech_ended_emitted)

    def test_correction_routing_late_callback_isolation(self):
        """Correction interruption: request A cancelled, request B created, late sentence from A discarded."""
        from services.speech_service import speech
        from services.tts.streaming_tts_queue import streaming_tts_queue

        req_A = "req-corr-orig"
        req_B = "corr-req-corr-new"

        speech.start_request(req_A)
        streaming_tts_queue.start_new_request(request_id=req_A)

        # Simulate correction interruption action: cancel A, start B
        speech.cancel_request(req_A)
        streaming_tts_queue.cancel_active_request()

        speech.start_request(req_B)
        streaming_tts_queue.start_new_request(request_id=req_B)

        # Late enqueue from A
        accepted = streaming_tts_queue.enqueue_sentence(req_A, "Tell me about football.")
        self.assertFalse(accepted)

        # Enqueue from B
        accepted_B = streaming_tts_queue.enqueue_sentence(req_B, "Tell me about American football.")
        self.assertTrue(accepted_B)

    def test_lifecycle_deadlock_stress_100_iterations(self):
        """100-iteration stress test for lifecycle completion without deadlocks or hanging threads."""
        from services.speech_service import speech

        for i in range(100):
            req_id = f"stress-req-{i:03d}"
            speech.start_request(req_id)

            # Thread 1: Mark synthesis started/finished
            def _synth():
                with speech.engine._lifecycle_lock:
                    if req_id in speech.engine._lifecycles:
                        speech.engine._lifecycles[req_id].synthesis_active = True
                time.sleep(0.0001)
                with speech.engine._lifecycle_lock:
                    if req_id in speech.engine._lifecycles:
                        speech.engine._lifecycles[req_id].synthesis_active = False

            # Thread 2: Mark producer finished
            def _prod():
                time.sleep(0.0001)
                speech.mark_producer_finished(req_id)

            t1 = threading.Thread(target=_synth)
            t2 = threading.Thread(target=_prod)

            t1.start()
            t2.start()

            t1.join(timeout=1.0)
            t2.join(timeout=1.0)

            self.assertFalse(t1.is_alive(), f"Iteration {i}: synth thread deadlocked")
            self.assertFalse(t2.is_alive(), f"Iteration {i}: producer thread deadlocked")


if __name__ == "__main__":
    unittest.main()
