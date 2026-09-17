"""Shared event-builder helpers for graph/workflow instrumentation.

Every event dict shape (``{"type", "timestamp", ...}``) is defined ONCE here so
the fixed baseline, adaptive workflow, and tool-driven demo emit byte-identical
event structures. Metric/adaptation logic is never duplicated in callers.
"""

from __future__ import annotations

from typing import Any

from ekatra.observability.clock import default_now
from ekatra.observability.events import EventType

EventDict = dict[str, Any]

# Event types that only the adaptive workflow can produce.
ADAPTIVE_ONLY_TYPES = frozenset({
    EventType.AGENT_SPAWNED.value,
    EventType.AGENT_TERMINATED.value,
    EventType.TASK_REASSIGNED.value,
    EventType.TASK_PRIORITIZED.value,
    EventType.ADAPTATION_DECISION.value,
})

# Task lifecycle statuses considered terminal: no further work can be started.
# A workflow is complete only when every task sits in one of these.
TERMINAL_TASK_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


def workflow_reached_terminal_state(tasks: list[dict[str, Any]]) -> bool:
    """True when no task still has executable work remaining.

    Shared completion rule (fixed and adaptive use the same semantics): the
    workflow has reached its terminal execution state when every task is in a
    terminal status (``COMPLETED`` / ``FAILED`` / ``CANCELLED``). Any task in
    ``PENDING`` / ``ASSIGNED`` / ``RUNNING`` / ``RETRY`` still represents
    schedulable work, so completion is not reached.
    """
    return all(t.get("status") in TERMINAL_TASK_STATUSES for t in tasks)


def _event(event_type: EventType, timestamp: str | None, **data: Any) -> EventDict:
    return {"type": event_type.value, "timestamp": timestamp or default_now(), **data}


def workflow_started_event(
    project_description: str, timestamp: str | None = None
) -> EventDict:
    return _event(EventType.WORKFLOW_STARTED, timestamp, project_description=project_description)


def workflow_completed_event(
    final_step: str, timestamp: str | None = None
) -> EventDict:
    return _event(EventType.WORKFLOW_COMPLETED, timestamp, final_step=final_step)


def task_created_event(task: dict[str, Any]) -> EventDict:
    return _event(
        EventType.TASK_CREATED,
        task.get("created_at"),
        task_id=task["id"],
        role=task.get("role"),
        priority=task.get("priority"),
        complexity=task.get("complexity"),
    )


def task_assigned_event(task: dict[str, Any]) -> EventDict:
    return _event(
        EventType.TASK_ASSIGNED,
        task.get("assigned_at") or task.get("created_at"),
        task_id=task["id"],
        role=task.get("role"),
        agent_id=task.get("assigned_agent"),
    )


def task_started_event(task: dict[str, Any]) -> EventDict:
    return _event(
        EventType.TASK_STARTED,
        task.get("started_at"),
        task_id=task["id"],
        role=task.get("role"),
        agent_id=task.get("assigned_agent"),
    )


def task_completed_event(task: dict[str, Any]) -> EventDict:
    return _event(
        EventType.TASK_COMPLETED,
        task.get("completed_at"),
        task_id=task["id"],
        role=task.get("role"),
        agent_id=task.get("assigned_agent"),
    )


def task_failed_event(
    task: dict[str, Any], timestamp: str | None = None
) -> EventDict:
    return _event(
        EventType.TASK_FAILED,
        timestamp or task.get("completed_at"),
        task_id=task["id"],
        role=task.get("role"),
        agent_id=task.get("assigned_agent"),
        retry_count=task.get("retry_count", 0),
    )


def task_retried_event(
    task: dict[str, Any], timestamp: str | None = None
) -> EventDict:
    return _event(
        EventType.TASK_RETRIED,
        timestamp or task.get("started_at"),
        task_id=task["id"],
        role=task.get("role"),
        agent_id=task.get("assigned_agent"),
        retry_count=task.get("retry_count", 0),
    )


def agent_spawned_event(
    agent_id: str, role: str, timestamp: str | None = None
) -> EventDict:
    return _event(EventType.AGENT_SPAWNED, timestamp, agent_id=agent_id, role=role)


def agent_terminated_event(
    agent_id: str, role: str | None = None, timestamp: str | None = None
) -> EventDict:
    return _event(
        EventType.AGENT_TERMINATED, timestamp, agent_id=agent_id, role=role
    )


def task_reassigned_event(
    task_id: str,
    from_agent: str | None,
    to_agent: str,
    reason: str,
    timestamp: str | None = None,
) -> EventDict:
    return _event(
        EventType.TASK_REASSIGNED,
        timestamp,
        task_id=task_id,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
    )


def task_prioritized_event(
    task_id: str,
    previous_priority: int | None,
    new_priority: int,
    reason: str,
    timestamp: str | None = None,
) -> EventDict:
    return _event(
        EventType.TASK_PRIORITIZED,
        timestamp,
        task_id=task_id,
        previous_priority=previous_priority,
        new_priority=new_priority,
        reason=reason,
    )


def tool_executed_event(tool_call: dict[str, Any]) -> EventDict:
    return _event(
        EventType.TOOL_EXECUTED,
        tool_call.get("timestamp"),
        tool_name=tool_call.get("tool_name"),
        agent_id=tool_call.get("agent_id"),
        success=tool_call.get("success"),
        duration_ms=tool_call.get("duration_ms", 0.0),
        task_id=tool_call.get("task_id"),
    )


def decision_events(decision: dict[str, Any]) -> list[EventDict]:
    """Turn one serialized AdaptiveDecision into its orthogonal event set.

    Always emits an ``ADAPTATION_DECISION`` event; for SPAWN / TERMINATE /
    REASSIGN / PRIORITIZE it additionally emits the concrete action event so
    the fixed-vs-adaptive event schemas stay parallel (the fixed baseline
    simply never produces those types).
    """
    timestamp = decision.get("timestamp")
    decision_name = decision.get("decision")
    events: list[EventDict] = [
        _event(
            EventType.ADAPTATION_DECISION,
            timestamp,
            decision=decision_name,
            cycle=decision.get("cycle"),
            workload_score=decision.get("workload_score"),
            risk_score=decision.get("risk_score"),
            workload_level=decision.get("workload_level"),
            risk_level=decision.get("risk_level"),
            reason=decision.get("reason"),
            affected_role=decision.get("affected_role"),
            affected_agent=decision.get("affected_agent"),
            affected_task=decision.get("affected_task"),
        )
    ]

    resulting = decision.get("resulting_state") or {}
    role = decision.get("affected_role")

    if decision_name == "SPAWN":
        spawned = resulting.get("spawned_agent")
        if spawned:
            events.append(
                agent_spawned_event(spawned, role or "", timestamp)
            )
    elif decision_name == "TERMINATE":
        terminated = resulting.get("terminated_agent")
        if terminated:
            events.append(agent_terminated_event(terminated, role, timestamp))
    elif decision_name == "REASSIGN":
        task_id = resulting.get("reassigned_task")
        to_agent = resulting.get("to_agent")
        if task_id and to_agent:
            previous = decision.get("previous_state") or {}
            prior_agent = previous.get("assigned_agent")
            events.append(
                task_reassigned_event(
                    task_id,
                    prior_agent,
                    to_agent,
                    decision.get("reason", ""),
                    timestamp,
                )
            )
    elif decision_name == "PRIORITIZE":
        task_id = resulting.get("prioritized_task")
        if task_id:
            previous = decision.get("previous_state") or {}
            events.append(
                task_prioritized_event(
                    task_id,
                    previous.get("priority"),
                    resulting.get("priority"),
                    decision.get("reason", ""),
                    timestamp,
                )
            )
    return events


def task_lifecycle_events(
    task: dict[str, Any], *, include_created: bool = False
) -> list[EventDict]:
    """Produce the lifecycle events for a single final task record.

    Used when a workflow node has already transitioned a task and only the
    final record is at hand (start + complete, or plan-time created + assigned).
    """
    events: list[EventDict] = []
    if include_created:
        events.append(task_created_event(task))
        events.append(task_assigned_event(task))
    if task.get("started_at"):
        events.append(task_started_event(task))
    if task.get("status") == "COMPLETED" and task.get("completed_at"):
        events.append(task_completed_event(task))
    elif task.get("status") == "FAILED":
        events.append(task_failed_event(task))
    return events


def finalize_workflow_events(
    result: dict[str, Any], default_step: str
) -> dict[str, Any]:
    """Append WORKFLOW_COMPLETED only once the workflow is terminal.

    Uses the same shared rule as the adaptive workflow: the event is emitted
    only when no task still has executable work remaining (every task is
    ``COMPLETED`` / ``FAILED`` / ``CANCELLED``). Otherwise the final node
    reaching the end of the graph does not, by itself, produce the event.
    """
    events = list(result.get("observability_events", []))
    tasks = result.get("tasks") or []
    if workflow_reached_terminal_state(tasks):
        events.append(
            workflow_completed_event(result.get("current_step") or default_step)
        )
    result["observability_events"] = events
    return result


def with_workflow_completed(default_step: str):
    """Decorate a final graph node so it emits one WORKFLOW_COMPLETED event.

    Shared by the fixed baseline, adaptive, and tool-demo workflows so the
    termination event is emitted once, in exactly one place.
    """

    def decorator(node):
        def wrapped(state: Any) -> dict[str, Any]:
            result = node(state)
            return finalize_workflow_events(result, default_step)

        return wrapped

    return decorator


__all__ = [
    "ADAPTIVE_ONLY_TYPES",
    "TERMINAL_TASK_STATUSES",
    "agent_spawned_event",
    "agent_terminated_event",
    "decision_events",
    "finalize_workflow_events",
    "with_workflow_completed",
    "task_assigned_event",
    "task_completed_event",
    "task_created_event",
    "task_failed_event",
    "task_lifecycle_events",
    "task_prioritized_event",
    "task_reassigned_event",
    "task_retried_event",
    "task_started_event",
    "tool_executed_event",
    "workflow_completed_event",
    "workflow_reached_terminal_state",
    "workflow_started_event",
]