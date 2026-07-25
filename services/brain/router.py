"""
services/brain/router.py
Phase 2.2 Brain Router for JARVIS M7.
Synchronous, CPU-only starting tier selection component for AI Brain requests.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


from services.tools.models import AgentRole, RoutingProfile


@dataclass
class RoutingDecision:
    starting_provider: str  # "groq", "ollama", "gemini", "skill", or "multi_agent"
    provider_chain: List[str]
    reason: str
    is_offline: bool = False
    route: str = "SINGLE_AGENT"  # "SINGLE_AGENT" | "MULTI_AGENT"
    confidence: float = 1.0
    complexity: str = "LOW"     # "LOW" | "MEDIUM" | "HIGH"
    selected_provider: Optional[str] = None
    selected_skills: List[str] = field(default_factory=list)
    policy_applied: str = "fast_path"  # "fast_path" | "tool_chain" | "research_synthesis"
    profile: RoutingProfile = RoutingProfile.SIMPLE


class BrainRouter:
    """
    Synchronous CPU-only decision component sitting between ConversationManager and ProviderManager.
    Determines starting tier order and multi-agent routing decisions based on QuestionClassifier metadata.
    """

    # Feature Flag: disabled by default per spec
    ENABLE_CONFIDENCE_ESCALATION: bool = False

    DEFAULT_CHAIN = ["groq", "gemini", "ollama"]
    PRIVATE_CHAIN = ["ollama", "groq", "gemini"]

    @staticmethod
    def expand_profile(profile: RoutingProfile) -> List[AgentRole]:
        """
        Canonical single source of truth for profile -> agent-sequence expansion.
        """
        if profile == RoutingProfile.SIMPLE:
            return [AgentRole.SYNTHESIZER]
        elif profile == RoutingProfile.RESEARCH:
            return [AgentRole.RESEARCH, AgentRole.SYNTHESIZER]
        elif profile == RoutingProfile.TOOL:
            return [AgentRole.TOOL, AgentRole.SYNTHESIZER]
        elif profile == RoutingProfile.FULL_REASONING:
            return [AgentRole.PLANNER, AgentRole.RESEARCH, AgentRole.TOOL, AgentRole.CRITIC, AgentRole.SYNTHESIZER]
        return [AgentRole.SYNTHESIZER]

    def __init__(self):
        # Latency & outcome history stats per provider (extended telemetry pattern)
        self._provider_stats: Dict[str, Dict[str, Any]] = {
            "groq": {"total_calls": 0, "successes": 0, "avg_latency_ms": 0.0},
            "ollama": {"total_calls": 0, "successes": 0, "avg_latency_ms": 0.0},
            "gemini": {"total_calls": 0, "successes": 0, "avg_latency_ms": 0.0},
        }

    def route(
        self,
        request_text: str,
        is_private: bool = False,
        skill_match_confidence: Optional[float] = None,
    ) -> RoutingDecision:
        """
        Synchronous, CPU-only routing decision.
        Consumes QuestionClassifier metadata to produce structured RoutingDecision.
        """
        text_clean = request_text.strip()

        from services.conversation.question_classifier import question_classifier
        classification = question_classifier.classify(text_clean)

        # Developer override check
        if classification.routing_hints.get("developer_override"):
            decision = RoutingDecision(
                starting_provider="multi_agent",
                provider_chain=["multi_agent"] + list(self.DEFAULT_CHAIN),
                reason="explicit developer override flag",
                is_offline=False,
                route="MULTI_AGENT",
                confidence=1.0,
                complexity=classification.estimated_complexity,
                selected_provider="multi_agent",
                selected_skills=classification.candidate_skills,
                policy_applied="research_synthesis",
                profile=RoutingProfile.FULL_REASONING
            )
            self._log_decision(decision)
            return decision

        # 1. Feature-flagged confidence escalation
        if self.ENABLE_CONFIDENCE_ESCALATION and skill_match_confidence is not None:
            if skill_match_confidence >= 0.85:
                decision = RoutingDecision(
                    starting_provider="skill",
                    provider_chain=[],
                    reason="high_confidence_skill_match",
                    is_offline=True,
                    route="SINGLE_AGENT",
                    confidence=skill_match_confidence,
                    complexity="LOW",
                    selected_provider="skill",
                    selected_skills=classification.candidate_skills,
                    policy_applied="fast_path",
                    profile=RoutingProfile.SIMPLE
                )
                self._log_decision(decision)
                return decision

        # 2. Privacy Mode Routing
        if is_private:
            decision = RoutingDecision(
                starting_provider="ollama",
                provider_chain=list(self.PRIVATE_CHAIN),
                reason="privacy_mode",
                is_offline=True,
                route="SINGLE_AGENT",
                confidence=1.0,
                complexity=classification.estimated_complexity,
                selected_provider="ollama",
                selected_skills=classification.candidate_skills,
                policy_applied="fast_path",
                profile=RoutingProfile.SIMPLE
            )
            self._log_decision(decision)
            return decision

        # 3. Structured Multi-Agent Routing (Phase 2.5b/2.5d)
        if (len(classification.candidate_tools) >= 2 and classification.routing_hints.get("multi_step_detected")) or classification.estimated_complexity == "HIGH":
            decision = RoutingDecision(
                starting_provider="multi_agent",
                provider_chain=["multi_agent"] + list(self.DEFAULT_CHAIN),
                reason=f"multiple dependent tools/skills detected ({', '.join(classification.candidate_skills)})",
                is_offline=False,
                route="MULTI_AGENT",
                confidence=0.95,
                complexity=classification.estimated_complexity,
                selected_provider="multi_agent",
                selected_skills=classification.candidate_skills,
                policy_applied="tool_chain" if classification.candidate_tools else "research_synthesis",
                profile=RoutingProfile.FULL_REASONING
            )
            self._log_decision(decision)
            return decision

        # 4. Default Single-Agent Fast Path
        decision = RoutingDecision(
            starting_provider="groq",
            provider_chain=list(self.DEFAULT_CHAIN),
            reason="default",
            is_offline=False,
            route="SINGLE_AGENT",
            confidence=0.90,
            complexity=classification.estimated_complexity,
            selected_provider="groq",
            selected_skills=classification.candidate_skills,
            policy_applied="fast_path",
            profile=RoutingProfile.SIMPLE
        )
        self._log_decision(decision)
        return decision

    def _log_decision(self, d: RoutingDecision) -> None:
        """Logs every routing decision in clean diagnostic format (Phase 2.5b Goal 1c)."""
        logger.info(
            f"[ROUTER] Route: {d.route} | Reason: {d.reason} | Complexity: {d.complexity} | "
            f"Candidate skills: {d.selected_skills} | Policy: {d.policy_applied} | Profile: {d.profile.value}"
        )

    def record_outcome(
        self, request_id: str, provider: str, latency_ms: float, success: bool
    ) -> None:
        """
        Feeds latency history for future routing decisions, extending existing telemetry pattern.
        """
        if provider not in self._provider_stats:
            self._provider_stats[provider] = {
                "total_calls": 0,
                "successes": 0,
                "avg_latency_ms": 0.0,
            }

        stats = self._provider_stats[provider]
        stats["total_calls"] += 1
        if success:
            stats["successes"] += 1

        # Exponential moving average for latency
        prev_avg = stats["avg_latency_ms"]
        if prev_avg == 0.0:
            stats["avg_latency_ms"] = float(latency_ms)
        else:
            stats["avg_latency_ms"] = (prev_avg * 0.8) + (latency_ms * 0.2)

        logger.debug(
            f"[BRAIN_ROUTER] Telemetry recorded | req={request_id} provider={provider} "
            f"latency={latency_ms:.1f}ms success={success} avg={stats['avg_latency_ms']:.1f}ms"
        )


# Global instance
brain_router = BrainRouter()
