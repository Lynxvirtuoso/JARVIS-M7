from services.reliability.models import FailureType


class InvalidRecoveryTransition(Exception):
    """Raised when an illegal RecoveryState transition is attempted."""
    pass


class RecoveryState:
    """
    Request-scoped recovery state machine. One instance per request —
    never a singleton, never shared between requests (architecture
    amendment A5). Construct a fresh instance per request needing
    recovery tracking; do not cache or reuse instances across requests.

    States: NORMAL, RETRYING, FALLBACK, RECOVERED, FAILED.
    Invalid transitions raise rather than silently no-op, so that any
    ownership-violation bug (e.g. two components trying to drive the
    same instance through conflicting transitions) surfaces immediately
    during development rather than failing silently in production.
    """

    VALID_STATES = {"NORMAL", "RETRYING", "FALLBACK", "RECOVERED", "FAILED"}

    # Allowed transitions: current_state -> set of legal next states
    ALLOWED_TRANSITIONS = {
        "NORMAL": {"RETRYING"},
        "RETRYING": {"RECOVERED", "FALLBACK", "FAILED"},
        "FALLBACK": {"RECOVERED", "FAILED"},
        "RECOVERED": {"NORMAL"},
        "FAILED": set(),  # terminal - no transitions out
    }

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.state = "NORMAL"
        self.history = [("NORMAL", None)]

    def transition_to(self, new_state: str, failure_type: FailureType = None) -> None:
        if new_state not in self.VALID_STATES:
            raise InvalidRecoveryTransition(
                f"'{new_state}' is not a valid RecoveryState state."
            )
        allowed = self.ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidRecoveryTransition(
                f"Illegal transition: {self.state} -> {new_state} "
                f"(request_id={self.request_id})"
            )
        self.state = new_state
        self.history.append((new_state, failure_type))
