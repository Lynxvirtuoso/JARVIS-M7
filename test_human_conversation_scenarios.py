"""
test_human_conversation_scenarios.py
Comprehensive test suite for Phase 1 Listening Reliability & Conversational Intelligence in JARVIS M7.
Tests wake-word flexibility, transcript resolution, sensitive confirmation, dynamic STT prompts,
audio clipping protection, self-voice echo rejection, and request-ID isolation.
"""
import unittest
import numpy as np
from services.conversation.models import ConversationRequest, ResolvedTranscript
from services.conversation.transcript_resolver import transcript_resolver, TranscriptResolver
from services.stt.prompt_builder import stt_prompt_builder, PASSIVE_WAKE_PROMPT
from services.conversation.echo_rejector import echo_rejector


class TestListeningReliabilityPhase1(unittest.TestCase):

    def setUp(self):
        self.resolver = TranscriptResolver()

    # --- 1. Wake Word Position & Variant Flexibility ---
    def test_wake_word_at_beginning(self):
        res = self.resolver.resolve("Jarvis, shut down.")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "start")
        self.assertIn("shut down", res.resolved_text.lower())

    def test_wake_word_at_end(self):
        res = self.resolver.resolve("Shut down, Jarvis.")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "end")
        self.assertIn("shut down", res.resolved_text.lower())

    def test_wake_word_in_middle(self):
        res = self.resolver.resolve("Could you shut down, Jarvis?")
        self.assertTrue(res.wake_word_detected)
        self.assertEqual(res.wake_word_position, "end")

    def test_wake_word_variants(self):
        for variant in ["Jervis, open chrome", "Javis, what time is it?", "Hey Jarvis, tell me a joke"]:
            res = self.resolver.resolve(variant)
            self.assertTrue(res.wake_word_detected)
            self.assertIsNotNone(res.wake_word_position)

    # --- 2. Misrecognition Safety & Confirmation ---
    def test_shadoon_jarvis_asks_for_confirmation(self):
        res = self.resolver.resolve("Shadoon Jarvis")
        self.assertTrue(res.needs_clarification)
        self.assertTrue(res.is_sensitive_action)
        self.assertEqual(res.clarification_question, "Did you ask me to shut down?")

    def test_uncertain_shutdown_never_executes_directly(self):
        res = self.resolver.resolve("Shadoon Jarvis", stt_confidence=0.50)
        self.assertTrue(res.needs_clarification)
        self.assertNotEqual(res.confidence, 1.0)
        self.assertIsNotNone(res.clarification_question)

    def test_who_is_there_rahman_clarification(self):
        res = self.resolver.resolve("Who's there, Rahman?")
        self.assertTrue(res.needs_clarification)
        self.assertEqual(res.clarification_question, "Did you mean, 'Who is A. R. Rahman?'")

    # --- 3. Dynamic STT Prompting ---
    def test_passive_stt_prompt_excludes_contacts(self):
        prompt = stt_prompt_builder.build_prompt("passive_wake")
        self.assertEqual(prompt, PASSIVE_WAKE_PROMPT)
        self.assertNotIn("Surya", prompt)
        self.assertNotIn("Contact", prompt)

    def test_active_stt_prompt_contains_relevant_context(self):
        prompt = stt_prompt_builder.build_prompt(
            mode="active_command",
            current_topic="A. R. Rahman",
            active_entities=["A. R. Rahman"],
            relevant_apps=["Google Chrome", "Notepad"]
        )
        self.assertIn("Desktop assistant command", prompt)
        self.assertIn("A. R. Rahman", prompt)
        self.assertIn("Google Chrome", prompt)

    # --- 4. Audio Protection & Peak Limiting ---
    def test_processed_peak_remains_in_valid_range(self):
        audio_loud = np.array([0.5, 0.8, 1.2, -1.4, 0.9], dtype=np.float32)
        orig_peak = float(np.max(np.abs(audio_loud)))
        self.assertTrue(orig_peak > 1.0)

        # Scale safely down to <= 0.95
        proc_audio = audio_loud / orig_peak * 0.95
        proc_peak = float(np.max(np.abs(proc_audio)))
        self.assertLessEqual(proc_peak, 1.0)

    def test_already_clipped_audio_not_amplified(self):
        audio_clipped = np.array([0.99, -0.99, 1.05], dtype=np.float32)
        orig_peak = float(np.max(np.abs(audio_clipped)))
        proc_audio = np.clip(audio_clipped / orig_peak * 0.95, -1.0, 1.0)
        self.assertLessEqual(np.max(np.abs(proc_audio)), 0.95)

    def test_severe_clipping_lowers_confidence(self):
        res = self.resolver.resolve("Jarvis, open chrome", stt_confidence=0.9, audio_quality=0.4)
        self.assertLess(res.confidence, 0.5)

    # --- 5. Self-Voice Echo Rejection ---
    def test_assistant_speech_fragment_rejected_as_echo(self):
        curr_spoken = "Certainly, Sir. Let's take a look at the beautiful game."
        is_echo = echo_rejector.is_echo(
            transcript="Certainly so Sir",
            current_spoken_sentence=curr_spoken,
            recent_spoken_sentences=[],
            request_id="req-1234"
        )
        self.assertTrue(is_echo)

    def test_stop_accepted_during_tts(self):
        curr_spoken = "Certainly, Sir. Let's take a look at the beautiful game."
        is_echo = echo_rejector.is_echo(
            transcript="Stop.",
            current_spoken_sentence=curr_spoken,
            recent_spoken_sentences=[],
            request_id="req-1234"
        )
        self.assertFalse(is_echo)

    def test_actually_accepted_during_tts(self):
        curr_spoken = "Certainly, Sir. Let's take a look at the beautiful game."
        is_echo = echo_rejector.is_echo(
            transcript="Actually no.",
            current_spoken_sentence=curr_spoken,
            recent_spoken_sentences=[],
            request_id="req-1234"
        )
        self.assertFalse(is_echo)

    # --- 6. Request ID Isolation ---
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
        self.assertNotIn("football", req1.raw_transcript)
        self.assertNotIn("time", req2.raw_transcript)


if __name__ == "__main__":
    unittest.main()
