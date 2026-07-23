"""
test_acknowledgement_and_sanitizer.py
Comprehensive unit test suite for AcknowledgementService, AcknowledgementIntent,
TTS Sanitizer (sanitize_for_tts), and Safe Sentence Buffer splitting.
"""
import unittest
from services.acknowledgement_intent import AcknowledgementIntent
from services.acknowledgement_service import AcknowledgementService
from services.tts.sanitizer import sanitize_for_tts
from services.tts.sentence_buffer import SentenceBuffer


class TestAcknowledgementIntentAndService(unittest.TestCase):

    def setUp(self):
        self.service = AcknowledgementService(history_size=5)

    def test_football_classification_and_no_search_when_use_web_false(self):
        intent = self.service.classify("Jarvis, tell me about football.", brain_route="simple_chat", use_web=False)
        phrase = self.service.generate("Jarvis, tell me about football.", brain_route="simple_chat", use_web=False)
        self.assertEqual(intent, AcknowledgementIntent.GENERAL_EXPLANATION)
        self.assertIsNotNone(phrase)
        # MUST NEVER contain search claims
        for forbidden in ["searching", "check online", "latest information", "look up"]:
            self.assertNotIn(forbidden, phrase.lower())
        self.assertIn("beautiful game", phrase.lower())

    def test_joke_classification(self):
        intent = self.service.classify("Jarvis, tell me a joke.", brain_route="simple_chat", use_web=False)
        phrase = self.service.generate("Jarvis, tell me a joke.", brain_route="simple_chat", use_web=False)
        self.assertEqual(intent, AcknowledgementIntent.HUMOUR)
        self.assertIsNotNone(phrase)
        self.assertTrue(any(kw in phrase.lower() for kw in ["humour", "humor", "comedy", "punchline"]))

    def test_piano_classification(self):
        intent = self.service.classify("Jarvis, explain how a piano works.", brain_route="simple_chat", use_web=False)
        phrase = self.service.generate("Jarvis, explain how a piano works.", brain_route="simple_chat", use_web=False)
        self.assertEqual(intent, AcknowledgementIntent.MUSIC)
        self.assertIsNotNone(phrase)
        self.assertIn("open the lid", phrase.lower())

    def test_coding_classification(self):
        intent = self.service.classify("Jarvis, help me fix this Python error.", brain_route="complex_reasoning", use_web=False)
        phrase = self.service.generate("Jarvis, help me fix this Python error.", brain_route="complex_reasoning", use_web=False)
        self.assertEqual(intent, AcknowledgementIntent.CODING)
        self.assertIsNotNone(phrase)
        self.assertTrue(any(kw in phrase.lower() for kw in ["bug", "logic", "debug", "breaking"]))

    def test_current_weather_with_use_web_true(self):
        intent = self.service.classify("Jarvis, what is the current weather?", brain_route="current_information", use_web=True)
        phrase = self.service.generate("Jarvis, what is the current weather?", brain_route="current_information", use_web=True)
        self.assertEqual(intent, AcknowledgementIntent.CURRENT_SEARCH)
        self.assertIsNotNone(phrase)
        self.assertTrue(any(kw in phrase.lower() for kw in ["information", "verify", "current", "latest"]))

    def test_current_weather_with_use_web_false_prohibits_search_phrase(self):
        intent = self.service.classify("Jarvis, what is the current weather?", brain_route="simple_chat", use_web=False)
        phrase = self.service.generate("Jarvis, what is the current weather?", brain_route="simple_chat", use_web=False)
        self.assertNotEqual(intent, AcknowledgementIntent.CURRENT_SEARCH)
        self.assertIsNotNone(phrase)
        for forbidden in ["searching", "check online", "latest information", "look up"]:
            self.assertNotIn(forbidden, phrase.lower())

    def test_instant_time_request_skips_acknowledgement(self):
        self.assertTrue(self.service.should_skip("Jarvis, what is the time?"))
        phrase = self.service.generate("Jarvis, what is the time?")
        self.assertIsNone(phrase)

    def test_direct_action_skips_acknowledgement(self):
        self.assertTrue(self.service.should_skip("Jarvis, open Chrome", command_name="open_app"))
        phrase = self.service.generate("Jarvis, open Chrome", command_name="open_app")
        self.assertIsNone(phrase)

    def test_rotation_avoids_recently_used_phrases(self):
        req = "Tell me a joke."
        p1 = self.service.generate(req, use_web=False, seed=42)
        p2 = self.service.generate(req, use_web=False, seed=43)
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)
        # Recorded phrases should be tracked in recent history
        self.assertIn(p1, self.service._recent_phrases)


class TestTTSSanitizer(unittest.TestCase):

    def test_sanitize_markdown_formatting(self):
        raw = "### **FIFA** World Cup\n- **Objective:** Score more goals.\n[Official site](https://example.com)"
        sanitized = sanitize_for_tts(raw)
        self.assertNotIn("**", sanitized)
        self.assertNotIn("###", sanitized)
        self.assertNotIn("[Official site]", sanitized)
        self.assertIn("FIFA World Cup", sanitized)
        self.assertIn("Objective: Score more goals", sanitized)
        self.assertIn("Official site", sanitized)


class TestSentenceBufferSplitting(unittest.TestCase):

    def test_split_does_not_end_with_dangling_fragment(self):
        buf = SentenceBuffer(minimum_chars=20, maximum_chars=40)
        # Create a text with 'and a 10' near position 40
        long_text = "The team played exceptionally well and a 10 minute rest was taken by everyone"
        sentences = buf.add_chunk(long_text) + buf.flush()
        self.assertTrue(len(sentences) >= 1)
        for s in sentences:
            self.assertFalse(s.strip().endswith("and a 10"))
            self.assertFalse(s.strip().endswith("with the"))
            self.assertFalse(s.strip().endswith("because the"))


if __name__ == "__main__":
    unittest.main()
