"""Task model and lifecycle.

Implements the documented task metadata and states from
``docs/05-task-state-model.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ekatra.agents.base import Role


class TaskStatus(str, Enum):
    """Task lifecycle states (see ``docs/05-task-state-model.md``)."""

    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    CANCELLED = "CANCELLED"


class Task(BaseModel):
    """Structured metadata for a single development task."""

    id: str
    description: str
    role: Role
    priority: int = Field(default=1, ge=1, le=3)
    complexity: int = Field(default=1, ge=1, le=5)
    dependencies: list[str] = Field(default_factory=list)
    risk: int = Field(default=0, ge=0, le=100)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str | None = None
    retry_count: int = Field(default=0, ge=0)
    output: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    priority_history: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-safe dict for the shared state."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Rebuild a task from a state dict."""
        return cls.model_validate(data)


__all__ = ["Task", "TaskStatus"]