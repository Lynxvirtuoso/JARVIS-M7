"""
test_sentence_buffer_and_streaming_tts.py
Comprehensive unit tests for SentenceBuffer and StreamingTTSQueue.
"""
import unittest
from services.tts.sentence_buffer import SentenceBuffer
from services.tts.streaming_tts_queue import StreamingTTSQueue, TTSStreamItem


class TestSentenceBuffer(unittest.TestCase):

    def _collect(self, buf: SentenceBuffer, text: str):
        """Helper: add_chunk then flush, returning combined list."""
        return buf.add_chunk(text) + buf.flush()

    def test_chunks_combine_into_complete_sentences(self):
        buf = SentenceBuffer(minimum_chars=20)
        s1 = buf.add_chunk("Foot")
        s2 = buf.add_chunk("ball is a ")
        s3 = buf.add_chunk("team sport. It ")
        # Only the complete sentence should have been emitted
        self.assertEqual(s1 + s2 + s3, ["Football is a team sport."])

    def test_multiple_sentences_in_one_chunk(self):
        buf = SentenceBuffer(minimum_chars=15)
        res = self._collect(buf, "Football is a great sport. It is played by two teams of eleven players.")
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0], "Football is a great sport.")
        self.assertEqual(res[1], "It is played by two teams of eleven players.")

    def test_incomplete_sentence_remains_buffered(self):
        buf = SentenceBuffer(minimum_chars=20)
        res = buf.add_chunk("Football is a great")
        self.assertEqual(res, [])
        flushed = buf.flush()
        self.assertEqual(flushed, ["Football is a great"])

    def test_decimal_3_14_does_not_split(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "The value of pi is approximately 3.14 for basic geometry calculations.")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], "The value of pi is approximately 3.14 for basic geometry calculations.")

    def test_name_initials_do_not_split(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "The music composer A. R. Rahman has won global awards.")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], "The music composer A. R. Rahman has won global awards.")

    def test_abbreviation_dr_smith_does_not_split(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "Dr. Smith visited the laboratory today to inspect the results.")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], "Dr. Smith visited the laboratory today to inspect the results.")

    def test_long_sentence_splits_at_safe_boundary(self):
        # Use a long text with NO terminal punctuation so the max_chars boundary split is triggered
        buf = SentenceBuffer(minimum_chars=20, maximum_chars=60)
        long_text = "Football is a very popular global team sport played with a spherical ball on a large rectangular grass pitch"
        res = self._collect(buf, long_text)
        # With max_chars=60 and no terminal punctuation, it must split into 2+ parts
        self.assertTrue(len(res) >= 2)
        combined = " ".join(res)
        self.assertIn("Football is a very popular", combined)

    def test_empty_chunks_ignored(self):
        buf = SentenceBuffer()
        res = buf.add_chunk("")
        self.assertEqual(res, [])

    def test_whitespace_stripped(self):
        buf = SentenceBuffer(minimum_chars=15)
        res = self._collect(buf, "  Football is a great sport.  ")
        self.assertTrue(len(res) == 1)
        self.assertEqual(res[0], "Football is a great sport.")

    def test_first_sentence_minimum_chars(self):
        buf = SentenceBuffer(minimum_chars=40, first_sentence_minimum_chars=15)
        res = self._collect(buf, "Football is a great sport.")
        self.assertEqual(res, ["Football is a great sport."])

    def test_question_mark_terminates_sentence(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "Is football popular? Yes it is.")
        self.assertEqual(res[0], "Is football popular?")

    def test_exclamation_terminates_sentence(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "What a great game! Everyone loved it.")
        self.assertEqual(res[0], "What a great game!")

    def test_reset_clears_state(self):
        buf = SentenceBuffer(minimum_chars=10)
        buf.add_chunk("Football is a great sport.")
        buf.reset()
        self.assertEqual(buf._buffer, "")
        self.assertTrue(buf._is_first_sentence)

    def test_incremental_token_streaming(self):
        """Simulate token-by-token streaming as an LLM would generate."""
        buf = SentenceBuffer(minimum_chars=18)
        tokens = ["Football", " is", " a", " great", " sport.", " It", " is", " fun."]
        all_sentences = []
        for tok in tokens:
            all_sentences.extend(buf.add_chunk(tok))
        all_sentences.extend(buf.flush())
        self.assertIn("Football is a great sport.", all_sentences)
        self.assertIn("It is fun.", all_sentences)

    def test_abbreviation_e_g_does_not_split(self):
        buf = SentenceBuffer(minimum_chars=10)
        res = self._collect(buf, "Some examples e.g. football and cricket are popular sports.")
        self.assertEqual(len(res), 1)


class TestStreamingTTSQueue(unittest.TestCase):

    def test_request_id_isolation_and_stale_rejection(self):
        q = StreamingTTSQueue(max_size=5)
        id1 = q.start_new_request()
        self.assertTrue(q.enqueue_sentence(id1, "Sentence 1 from request 1"))

        id2 = q.start_new_request()
        # Old request ID should be rejected
        self.assertFalse(q.enqueue_sentence(id1, "Sentence 2 from request 1"))

        # New request should be accepted
        self.assertTrue(q.enqueue_sentence(id2, "Sentence 1 from request 2"))
        item = q.get_next_item(timeout=0.5)
        self.assertIsNotNone(item)
        self.assertEqual(item.request_id, id2)
        self.assertEqual(item.text, "Sentence 1 from request 2")

    def test_cancel_active_request_clears_queue(self):
        q = StreamingTTSQueue(max_size=5)
        req_id = q.start_new_request()
        q.enqueue_sentence(req_id, "Sentence A")
        q.enqueue_sentence(req_id, "Sentence B")

        q.cancel_active_request()
        self.assertFalse(q.is_request_active(req_id))
        item = q.get_next_item(timeout=0.1)
        self.assertIsNone(item)

    def test_empty_sentence_not_enqueued(self):
        q = StreamingTTSQueue(max_size=5)
        req_id = q.start_new_request()
        self.assertFalse(q.enqueue_sentence(req_id, ""))
        self.assertFalse(q.enqueue_sentence(req_id, "   "))

    def test_sequence_order_is_preserved(self):
        q = StreamingTTSQueue(max_size=10)
        req_id = q.start_new_request()
        for i in range(5):
            q.enqueue_sentence(req_id, f"Sentence number {i} in the queue.")
        for i in range(5):
            item = q.get_next_item(timeout=0.5)
            self.assertIsNotNone(item)
            self.assertEqual(item.sequence, i)
            q.task_done()


if __name__ == "__main__":
    unittest.main()
