import unittest
import sys
from services.reliability.models import FailureType
from services.reliability.retry_context import RetryContext


class TestRetryContext(unittest.TestCase):
    def test_increment(self):
        """increment() on a fresh context returns 1, then 2, then 3 for repeated calls."""
        ctx = RetryContext("req-test-123")
        self.assertEqual(ctx.increment(FailureType.PROVIDER_TIMEOUT), 1)
        self.assertEqual(ctx.increment(FailureType.PROVIDER_TIMEOUT), 2)
        self.assertEqual(ctx.increment(FailureType.PROVIDER_TIMEOUT), 3)

    def test_count_for_never_incremented(self):
        """count_for() on a FailureType never incremented returns 0."""
        ctx = RetryContext("req-test-123")
        self.assertEqual(ctx.count_for(FailureType.PROVIDER_TIMEOUT), 0)

    def test_reset(self):
        """reset() sets the count back to 0, subsequent increment returns 1."""
        ctx = RetryContext("req-test-123")
        ctx.increment(FailureType.PROVIDER_TIMEOUT)
        ctx.increment(FailureType.PROVIDER_TIMEOUT)
        self.assertEqual(ctx.count_for(FailureType.PROVIDER_TIMEOUT), 2)
        
        ctx.reset(FailureType.PROVIDER_TIMEOUT)
        self.assertEqual(ctx.count_for(FailureType.PROVIDER_TIMEOUT), 0)
        self.assertEqual(ctx.increment(FailureType.PROVIDER_TIMEOUT), 1)

    def test_per_request_isolation(self):
        """Two separate RetryContext instances do not affect each other."""
        ctx1 = RetryContext("req-1")
        ctx2 = RetryContext("req-2")

        ctx1.increment(FailureType.PROVIDER_TIMEOUT)
        ctx1.increment(FailureType.PROVIDER_TIMEOUT)
        ctx1.increment(FailureType.PROVIDER_TIMEOUT)

        self.assertEqual(ctx1.count_for(FailureType.PROVIDER_TIMEOUT), 3)
        self.assertEqual(ctx2.count_for(FailureType.PROVIDER_TIMEOUT), 0)

    def test_revision_counter_uncoupled(self):
        """Import services.agents.coordinator and confirm MAX_REVISION_CAP and RetryContext are uncoupled."""
        import services.agents.coordinator as coordinator
        # Confirm coordinator has MAX_REVISION_CAP
        self.assertTrue(hasattr(coordinator, "MAX_REVISION_CAP"))
        
        # Assert coordinator does not import or use RetryContext yet
        self.assertNotIn("RetryContext", dir(coordinator))
        
        # Verify that RetryContext does not reference MAX_REVISION_CAP
        ctx = RetryContext("req-1")
        self.assertFalse(hasattr(ctx, "MAX_REVISION_CAP"))


if __name__ == "__main__":
    unittest.main()
