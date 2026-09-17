"""Adaptive decision model.

Defines the set of adaptation actions and the structured
:class:`AdaptiveDecision` record that documents every controller evaluation.
Records are produced deterministically, serialized to JSON-safe dicts, and
accumulated in ``EkatraState["adaptive_decisions"]``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timezone


class AdaptiveAction(str, Enum):
    """The discrete set of adaptive orchestration actions."""

    CONTINUE = "CONTINUE"
    SPAWN = "SPAWN"
    TERMINATE = "TERMINATE"
    REASSIGN = "REASSIGN"
    PRIORITIZE = "PRIORITIZE"


class AdaptiveDecision(BaseModel):
    """A structured record documenting one controller evaluation.

    Attributes:
        timestamp: ISO-8601 evaluation time.
        cycle: Which adaptive cycle this evaluation occurred during (1-based).
        decision: The action selected by the controller.
        workload_score: The 0-100 workload score at evaluation time.
        risk_score: The 0-100 risk score at evaluation time.
        workload_level: Human-readable workload level.
        risk_level: Human-readable risk level.
        reason: Deterministic human-readable justification for the action.
        affected_role: The role being adapted (if applicable).
        affected_agent: The agent ID created or terminated (if applicable).
        affected_task: The task being reprioritized or reassigned (if applicable).
        previous_state: Snapshot of key observable state before the action.
        resulting_state: Snapshot of the observable state after the action.
    """

    timestamp: str
    cycle: int = 1
    decision: AdaptiveAction = AdaptiveAction.CONTINUE
    workload_score: float = 0.0
    risk_score: float = 0.0
    workload_level: str = "NORMAL"
    risk_level: str = "NORMAL"
    reason: str = "No adaptive change required"
    affected_role: str | None = None
    affected_agent: str | None = None
    affected_task: str | None = None
    previous_state: dict[str, Any] = Field(default_factory=dict)
    resulting_state: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict suitable for state accumulation."""
        return self.model_dump(mode="json")

    @model_validator(mode="after")
    def _validate_action_fields(self) -> "AdaptiveDecision":
        action = self.decision
        if action is AdaptiveAction.SPAWN and not self.affected_role:
            raise ValueError("SPAWN requires affected_role")
        if action is AdaptiveAction.TERMINATE and not self.affected_agent:
            raise ValueError("TERMINATE requires affected_agent")
        if action is AdaptiveAction.REASSIGN and not self.affected_task:
            raise ValueError("REASSIGN requires affected_task")
        if action is AdaptiveAction.PRIORITIZE and not self.affected_task:
            raise ValueError("PRIORITIZE requires affected_task")
        return self


__all__ = ["AdaptiveAction", "AdaptiveDecision"]