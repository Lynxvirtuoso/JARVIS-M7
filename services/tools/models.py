"""
services/tools/models.py
Data structures and Enums for Phase 2.3 Tool Execution Layer (TEL).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class ValidationOutcome(Enum):
    COMPLETE_SUCCESS = "COMPLETE_SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    RECOVERABLE_FAILURE = "RECOVERABLE_FAILURE"
    FATAL_FAILURE = "FATAL_FAILURE"


@dataclass
class ToolMetadata:
    tool_name: str
    destructive: bool = False
    needs_confirmation: bool = False
    offline_capable: bool = True


@dataclass
class ToolStep:
    step_id: str
    tool_name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    destructive: bool = False
    expected_artifact: Optional[str] = None
    depends_on: Optional[str] = None
    condition: Optional[str] = None


@dataclass
class ExecutionPlan:
    plan_id: str
    request_id: str
    steps: List[ToolStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    cacheable: bool = True


@dataclass
class StepResult:
    step_id: str
    tool_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    artifact_found: bool = True
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class PlanConfirmation:
    requires_confirmation: bool
    confirmations_required: List[str] = field(default_factory=list)
    destructive_steps: List[str] = field(default_factory=list)


@dataclass
class PlanExecutionResult:
    plan_id: str
    request_id: str
    outcome: ValidationOutcome
    step_results: List[StepResult] = field(default_factory=list)
    spoken_summary: str = ""


class AgentRole(Enum):
    PLANNER = "Planner"
    RESEARCH = "Research"
    TOOL = "Tool"
    CRITIC = "Critic"
    SYNTHESIZER = "Synthesizer"


class RoutingProfile(Enum):
    SIMPLE = "SIMPLE"
    RESEARCH = "RESEARCH"
    TOOL = "TOOL"
    FULL_REASONING = "FULL_REASONING"


class CritiqueVerdict(Enum):
    PASSED = "PASSED"
    NEEDS_REVISION = "NEEDS_REVISION"
    FAILED = "FAILED"


class AgentStepStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


@dataclass
class AgentInput:
    request: str
    shared_context: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    previous_outputs: Dict[str, Any] = field(default_factory=dict)
    execution_constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    agent_role: AgentRole
    reasoning: str = ""
    structured_result: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    suggested_next_action: Optional[str] = None
    status: AgentStepStatus = AgentStepStatus.SUCCESS
    output: Any = None
    context_writes: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    step_id: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class AgentStep:
    step_id: str
    agent_role: AgentRole
    depends_on: Optional[str] = None
    condition: Optional[str] = None
    requires_memory: bool = False
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningPlan:
    plan_id: str
    request_id: str
    steps: List[AgentStep] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Alias AgentResult to AgentOutput for full backwards compatibility
AgentResult = AgentOutput
