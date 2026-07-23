import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from services.acknowledgement_intent import AcknowledgementIntent
from services.brain.provider_manager import BrainRoute
from core.config import config
from core.logger import logger


@dataclass
class TelemetryContext:
    """Telemetry context for tracking active request across the pipeline."""
    request_id: str = field(default_factory=lambda: str(int(datetime.now().timestamp())))
    original_transcript: str = ""
    cleaned_command: str = ""
    acknowledgement_intent: Optional[AcknowledgementIntent] = None
    brain_route: Optional[BrainRoute] = None
    use_web: bool = False
    provider: str = ""
    command_name: str = ""
    timestamp: float = field(default_factory=time.time)


def get_thread_telemetry_context() -> TelemetryContext:
    """Get or create a telemetry context for the current thread."""
    if not hasattr(telemetry_contexts, '_local'):
        telemetry_contexts._local = threading.local()

    if not hasattr(telemetry_contexts._local, 'context'):
        telemetry_contexts._local.context = TelemetryContext()

    return telemetry_contexts._local.context


class TelemetryManager:
    """Enhanced telemetry manager with request context tracking."""

    def __init__(self):
        # Thread-local storage for active telemetry context
        self._local = threading.local()
        # Global registry of recent acknowledgements for rotation
        self._recent_acknowledgements = deque(maxlen=getattr(config, 'get', lambda k, d: d)('acknowledgement_recent_history_size', 5))

    def start_new_request(self, transcript: str) -> str:
        """Start a new request tracking session.

        Args:
            transcript: The original user transcript

        Returns:
            The request_id for this session
        """
        context = self._get_context()
        context.request_id = str(int(datetime.now().timestamp()))
        context.original_transcript = transcript
        context.timestamp = time.time()

        logger.debug(f"Started new telemetry context: request_id={context.request_id}, transcript={transcript}")
        return context.request_id

    def update_context(
        self,
        *,
        original_transcript: str = None,
        cleaned_command: str = None,
        acknowledgement_intent: AcknowledgementIntent = None,
        brain_route: BrainRoute = None,
        use_web: bool = None,
        provider: str = None,
        command_name: str = None,
    ):
        """Update telemetry context with additional information."""
        context = self._get_context()

        if original_transcript is not None:
            context.original_transcript = original_transcript
        if cleaned_command is not None:
            context.cleaned_command = cleaned_command
        if acknowledgement_intent is not None:
            context.acknowledgement_intent = acknowledgement_intent
        if brain_route is not None:
            context.brain_route = brain_route
        if use_web is not None:
            context.use_web = use_web
        if provider is not None:
            context.provider = provider
        if command_name is not None:
            context.command_name = command_name

        logger.debug(
            f"Updated telemetry context (ID: {context.request_id}) with "
            f"intent={acknowledgement_intent}, route={brain_route}, "
            f"use_web={use_web}, provider={provider}"
        )

    def track_acknowledgement(self, phrase: str, context: TelemetryContext = None):
        """Track acknowledgement usage for rotation control."""
        if not phrase:
            return

        if context is None:
            context = self._get_context()

        # Check if this phrase was used recently
        if phrase in self._recent_acknowledgements:
            logger.debug(f"Acknowledgement phrase used recently (ID: {context.request_id}): {phrase}")

        # Add to recent acknowledgements
        self._recent_acknowledgements.append((context.request_id, phrase, datetime.now().isoformat()))

        # Log for analytics
        logger.info(
            f"Acknowledgement logged (ID: {context.request_id}): "
            f"phrase='{phrase}', intent={context.acknowledgement_intent}, "
            f"route={context.brain_route}, use_web={context.use_web}"
        )

    def get_context(self) -> TelemetryContext:
        """Get the current telemetry context."""
        return self._get_context()

    def _get_context(self) -> TelemetryContext:
        """Get or create a telemetry context for the current thread."""
        if not hasattr(self._local, 'context'):
            self._local.context = TelemetryContext()
        return self._local.context

    def get_recent_acknowledgements(self) -> deque:
        """Get the recent acknowledgements deque."""
        return self._recent_acknowledgements


# Global telemetry manager instance
telemetry_contexts = type('obj', (object,), {
    '_local': None,
    '_recent_acknowledgements': deque(maxlen=5),
    'get_context': lambda self, thread_local=None, _get_context=None: (
        thread_local.context if thread_local and hasattr(thread_local, 'context') 
        else TelemetryContext()
    ),
    'get_recent_acknowledgements': lambda self, _recent_acknowledgements=None: _recent_acknowledgements
})()

telemetry_manager = TelemetryManager()