from dataclasses import dataclass, field

@dataclass
class BrainResult:
    text: str = ""
    provider: str = ""
    success: bool = True
    error: str = ""
    error_type: str = ""
    thinking: str = ""
    metadata: dict = field(default_factory=dict)


class BrainProvider:
    provider_id: str

    def think(self, text: str, history: list[dict] = None) -> BrainResult:
        """
        Sends the text + context history to the brain provider and retrieves response.
        """
        raise NotImplementedError

    def health(self) -> tuple[bool, str]:
        """
        Returns (is_healthy, status_message).
        """
        raise NotImplementedError


def format_user_facts_for_prompt() -> str:
    from core.database import db
    facts = db.get_memory("user_facts", default=[])
    if facts:
        return f" Known facts about the user: {'; '.join(facts)}."
    return ""


def get_uncertainty_guardrail() -> str:
    return " If you are not confident about specific facts, statistics, dates, or numbers, say so clearly rather than stating a specific number with false confidence."

