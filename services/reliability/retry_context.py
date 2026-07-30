from services.reliability.models import FailureType


class RetryContext:
    """
    Per-request retry counter store. One instance per request — never
    shared between requests, and never merged with AgentCoordinator's
    MAX_REVISION_CAP / revision_count (which remains exclusively for
    Critic revisions, per architecture amendment A3).

    This class only counts. It does not decide whether to retry — that
    is RetryPolicy's job (a later task). It does not perform any retry
    itself — that is the calling owner's job.
    """

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.retry_counts: dict[FailureType, int] = {}

    def increment(self, failure_type: FailureType) -> int:
        """Increment and return the new count for this failure type."""
        current = self.retry_counts.get(failure_type, 0)
        new_count = current + 1
        self.retry_counts[failure_type] = new_count
        return new_count

    def count_for(self, failure_type: FailureType) -> int:
        """Return the current count for this failure type (0 if never incremented)."""
        return self.retry_counts.get(failure_type, 0)

    def reset(self, failure_type: FailureType) -> None:
        """Reset the counter for this failure type back to 0."""
        self.retry_counts[failure_type] = 0
