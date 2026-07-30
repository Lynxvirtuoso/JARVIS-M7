import unittest
from services.reliability.models import FailureType
from services.reliability.recovery_state import RecoveryState, InvalidRecoveryTransition


class TestRecoveryState(unittest.TestCase):
    def test_initial_state(self):
        """A fresh RecoveryState starts in 'NORMAL'."""
        state = RecoveryState("req-test-123")
        self.assertEqual(state.state, "NORMAL")
        self.assertEqual(state.history, [("NORMAL", None)])

    def test_valid_sequence_normal_retrying_recovered(self):
        """Valid sequence NORMAL -> RETRYING -> RECOVERED -> NORMAL succeeds."""
        state = RecoveryState("req-test-123")
        state.transition_to("RETRYING", FailureType.PROVIDER_TIMEOUT)
        self.assertEqual(state.state, "RETRYING")
        
        state.transition_to("RECOVERED")
        self.assertEqual(state.state, "RECOVERED")
        
        state.transition_to("NORMAL")
        self.assertEqual(state.state, "NORMAL")
        self.assertEqual(state.history, [
            ("NORMAL", None),
            ("RETRYING", FailureType.PROVIDER_TIMEOUT),
            ("RECOVERED", None),
            ("NORMAL", None)
        ])

    def test_valid_sequence_failed(self):
        """Valid sequence NORMAL -> RETRYING -> FALLBACK -> FAILED succeeds."""
        state = RecoveryState("req-test-123")
        state.transition_to("RETRYING", FailureType.PROVIDER_QUOTA_EXHAUSTED)
        state.transition_to("FALLBACK")
        state.transition_to("FAILED", FailureType.PROVIDER_UNAVAILABLE)
        self.assertEqual(state.state, "FAILED")

    def test_invalid_transition(self):
        """An invalid transition raises InvalidRecoveryTransition."""
        state = RecoveryState("req-test-123")
        with self.assertRaises(InvalidRecoveryTransition):
            state.transition_to("FAILED")  # Skipping RETRYING

    def test_transition_out_of_failed(self):
        """Attempting any transition out of FAILED raises InvalidRecoveryTransition."""
        state = RecoveryState("req-test-123")
        state.transition_to("RETRYING")
        state.transition_to("FAILED")
        
        with self.assertRaises(InvalidRecoveryTransition):
            state.transition_to("NORMAL")

    def test_independence(self):
        """Two separate RecoveryState instances are independent objects."""
        state1 = RecoveryState("req-1")
        state2 = RecoveryState("req-2")
        
        state1.transition_to("RETRYING")
        self.assertEqual(state1.state, "RETRYING")
        self.assertEqual(state2.state, "NORMAL")
        self.assertIsNot(state1, state2)

    def test_no_singleton_methods(self):
        """Confirm RecoveryState has no get_instance, no class-level singleton attribute."""
        self.assertFalse(hasattr(RecoveryState, "get_instance"))
        self.assertFalse(hasattr(RecoveryState, "_instance"))


if __name__ == "__main__":
    unittest.main()
