from abc import ABC, abstractmethod

class BaseSkill(ABC):
    """
    Abstract Base Class for JARVIS skills.
    Any new capability should inherit from this class and be placed in the skills/ directory.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of what the skill does."""
        pass

    @abstractmethod
    def matches(self, command: str) -> bool:
        """
        Evaluate if the command matches this skill.
        Used as local regex/keyword matching fallback.
        """
        pass

    @abstractmethod
    def execute(self, command: str) -> str:
        """
        Execute the skill action.
        Returns a verbal response string for JARVIS to speak.
        """
        pass
