"""Lightweight structured event model.

Events are the raw observations of a workflow run. Each event is a small,
JSON-safe record:

.. code-block:: json

    {
        "type": "task_started",
        "timestamp": "2026-01-01T00:00:00.000000+00:00",
        "task_id": "TASK-2",
        "agent_id": "BACKEND-1"
    }

Only the event types below are used (docs/04 and docs/05); no dozens of ad-hoc
types are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """The fixed, minimal set of observability event types."""

    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRIED = "task_retried"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_TERMINATED = "agent_terminated"
    TASK_REASSIGNED = "task_reassigned"
    TASK_PRIORITIZED = "task_prioritized"
    ADAPTATION_DECISION = "adaptation_decision"
    TOOL_EXECUTED = "tool_executed"
    QUALITY_OBSERVATION = "quality_observation"


@dataclass(frozen=True)
class Event:
    """A single structured, JSON-safe observability event."""

    type: EventType
    timestamp: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat, JSON-safe event dict."""
        return {"type": self.type.value, "timestamp": self.timestamp, **self.data}

    def __repr__(self) -> str:
        return f"<Event {self.type.value} @ {self.timestamp}>"


def make_event(
    event_type: EventType,
    timestamp: str,
    **data: Any,
) -> Event:
    """Create an event; ``timestamp`` is an ISO-8601 UTC string."""
    return Event(type=event_type, timestamp=timestamp, data=dict(data))


class EventLog:
    """Ordered, append-only collection of events."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self._events: list[Event] = list(events or [])

    def add(self, event: Event) -> Event:
        self._events.append(event)
        return event

    def extend(self, events: list[Event]) -> None:
        self._events.extend(events)

    def of_type(self, event_type: EventType) -> list[Event]:
        return [e for e in self._events if e.type is event_type]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)


__all__ = ["Event", "EventLog", "EventType", "make_event"]