"""Agent communication and coordination infrastructure.

Provides the structured message model
(:class:`~ekatra.orchestration.message.AgentMessage`) and the in-memory
:class:`~ekatra.orchestration.bus.MessageBus` so agents can exchange structured
messages during the fixed workflow in a deterministic, observable way.

Also provides the adaptive orchestration components for Milestone 5:

- :class:`~ekatra.orchestration.observer.SystemObservation` — per-role workload and risk observation
- :class:`~ekatra.orchestration.workload.WorkloadCalculator` — deterministic workload scoring
- :class:`~ekatra.orchestration.risk.RiskCalculator` — deterministic risk scoring
- :class:`~ekatra.orchestration.controller.AdaptiveController` — deterministic decision cascade
- :class:`~ekatra.orchestration.pool.AdaptiveAgentPool` — dynamic agent pool
- :class:`~ekatra.orchestration.adaptations.apply_decision` — decision execution
"""

from ekatra.orchestration.bus import MessageBus
from ekatra.orchestration.message import (
    BROADCAST_RECIPIENT,
    AgentMessage,
    MessageType,
)
from ekatra.orchestration.observer import (
    RoleObservation,
    SystemObservation,
    observe,
)
from ekatra.orchestration.workload import WorkloadCalculator, WorkloadConfig
from ekatra.orchestration.risk import RiskCalculator, RiskConfig
from ekatra.orchestration.controller import AdaptiveController, ControllerConfig
from ekatra.orchestration.pool import AdaptiveAgentPool
from ekatra.orchestration.adaptations import apply_decision, reassign_task
from ekatra.orchestration.decisions import AdaptiveAction, AdaptiveDecision

__all__ = [
    "AdaptiveAction",
    "AdaptiveController",
    "AdaptiveDecision",
    "AdaptiveAgentPool",
    "AgentMessage",
    "BROADCAST_RECIPIENT",
    "ControllerConfig",
    "MessageBus",
    "MessageType",
    "RiskCalculator",
    "RiskConfig",
    "RoleObservation",
    "SystemObservation",
    "WorkloadCalculator",
    "WorkloadConfig",
    "apply_decision",
    "observe",
    "reassign_task",
]
