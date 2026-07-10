import json
from abc import ABC, abstractmethod

class IntentResult:
    def __init__(self, action: str, target: str, confidence: float, requires_confirmation: bool = False):
        self.action = action
        self.target = target
        self.confidence = confidence
        self.requires_confirmation = requires_confirmation

    def to_dict(self):
        return {
            'action': self.action,
            'target': self.target,
            'confidence': self.confidence,
            'requires_confirmation': self.requires_confirmation
        }

class BaseIntentProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @abstractmethod
    def parse_intent(self, text: str) -> IntentResult:
        pass

    @abstractmethod
    def health(self) -> tuple[bool, str]:
        pass
