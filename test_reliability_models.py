import unittest
from services.reliability.models import FailureType, ReliabilityClassification


class TestReliabilityModels(unittest.TestCase):
    def test_construction_and_access(self):
        """Construct a ReliabilityClassification for each FailureType and check fields."""
        for failure in FailureType:
            rc = ReliabilityClassification(
                failure_type=failure,
                retryable=True,
                recoverable=False,
                fatal=True,
                reason=f"Test failure of type {failure.value}"
            )
            self.assertEqual(rc.failure_type, failure)
            self.assertTrue(rc.retryable)
            self.assertFalse(rc.recoverable)
            self.assertTrue(rc.fatal)
            self.assertEqual(rc.reason, f"Test failure of type {failure.value}")

    def test_equality(self):
        """Confirm two identical ReliabilityClassification instances compare equal."""
        rc1 = ReliabilityClassification(
            failure_type=FailureType.PROVIDER_TIMEOUT,
            retryable=True,
            recoverable=True,
            fatal=False,
            reason="timeout occurred"
        )
        rc2 = ReliabilityClassification(
            failure_type=FailureType.PROVIDER_TIMEOUT,
            retryable=True,
            recoverable=True,
            fatal=False,
            reason="timeout occurred"
        )
        rc3 = ReliabilityClassification(
            failure_type=FailureType.PROVIDER_TIMEOUT,
            retryable=False,
            recoverable=True,
            fatal=False,
            reason="timeout occurred"
        )
        self.assertEqual(rc1, rc2)
        self.assertNotEqual(rc1, rc3)

    def test_failure_type_count(self):
        """Confirm FailureType has exactly 16 members."""
        self.assertEqual(len(FailureType), 16)


if __name__ == "__main__":
    unittest.main()
