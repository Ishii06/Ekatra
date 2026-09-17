"""Unified, strategy-agnostic metrics computation.

One set of metric definitions serves BOTH the fixed baseline and the adaptive
workflow (docs/07 �4): ``compute_metrics`` derives every category from the
same final ``EkatraState`` + raw event log. Adaptive-only quantities (decisions,
spawn/termination, workload/risk series) are simply empty/zero for a fixed run —
the schema is identical by construction.

Metric categories:

* ``timing``   - workflow start/end from events
* ``task``     - totals, completion/waiting durations, queue length over time
* ``agent``    - counts, concurrency series, per-agent utilization
* ``adaptive`` - decisions, spawn/terminate/reassign/prioritize, workload/risk
* ``communication`` - message totals by type/sender/recipient
* ``tools``    - tool call totals by tool/agent/success/failure
* ``quality``  - recorded quality observations (no invented scores)

Raw observations (timestamps, events) are always preserved so metrics can be
recomputed later from experiment logs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ekatra.agents import FIXED_AGENT_IDS
from ekatra.observability.clock import parse_ts, seconds_between
from ekatra.observability.events import EventType


def _as_utc(value: Any) -> datetime | None:
    """Parse a timestamp and normalize naive values to UTC."""
    dt = parse_ts(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# -- timing -------------------------------------------------------------------


def compute_timing(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Workflow start/end timing derived from raw workflow events."""
    started = next(
        (e for e in events if e.get("type") == EventType.WORKFLOW_STARTED.value), None
    )
    completed = next(
        (e for e in events if e.get("type") == EventType.WORKFLOW_COMPLETED.value), None
    )
    return {
        "workflow_started_at": started["timestamp"] if started else None,
        "workflow_completed_at": completed["timestamp"] if completed else None,
        "duration_seconds": seconds_between(
            started["timestamp"] if started else None,
            completed["timestamp"] if completed else None,
        ),
        "event_count": len(events),
    }


# -- task metrics -------------------------------------------------------------


def _queue_series(
    tasks: list[dict[str, Any]],
    start: Any = None,
    end: Any = None,
) -> list[dict[str, Any]]:
    """Queue length over time.

    At each time ``t`` the queue is the number of created-but-not-completed
    tasks (``created_at <= t`` and (``completed_at`` missing or ``> t``)).
    """
    prepared = []
    for task in tasks:
        created = _as_utc(task.get("created_at"))
        completed = _as_utc(task.get("completed_at"))
        prepared.append((created, completed))
    prepared = [(c, e) for (c, e) in prepared if c is not None]

    times: set[datetime] = set()
    for created, completed in prepared:
        times.add(created)
        if completed is not None:
            times.add(completed)
    for boundary in (start, end):
        parsed = _as_utc(boundary)
        if parsed is not None:
            times.add(parsed)

    series: list[dict[str, Any]] = []
    previous: int | None = None
    for ts in sorted(times):
        count = sum(
            1
            for created, completed in prepared
            if created <= ts and not (completed is not None and completed <= ts)
        )
        if count != previous:
            series.append({"timestamp": ts.isoformat(), "queue_length": count})
            previous = count
    return series


def _task_durations(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-task execution durations (raw derived: started_at -> completed_at)."""
    durations: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("status") != "COMPLETED":
            continue
        durations.append({
            "task_id": task["id"],
            "role": task.get("role"),
            "duration_seconds": seconds_between(
                task.get("started_at"), task.get("completed_at")
            ),
        })
    return durations


def _task_waits(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-task waiting time (raw derived: created_at -> started_at)."""
    waits: list[dict[str, Any]] = []
    for task in tasks:
        if not task.get("started_at"):
            continue
        waits.append({
            "task_id": task["id"],
            "role": task.get("role"),
            "waiting_seconds": seconds_between(
                task.get("created_at"), task.get("started_at")
            ),
        })
    return waits


def compute_task_metrics(
    tasks: list[dict[str, Any]],
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Task totals, completion/waiting durations, and queue series."""
    completed = [t for t in tasks if t.get("status") == "COMPLETED"]
    failed = [t for t in tasks if t.get("status") == "FAILED"]
    retried = [t for t in tasks if (t.get("retry_count") or 0) > 0]
    total_retries = sum(t.get("retry_count") or 0 for t in tasks)

    durations = _task_durations(tasks)
    completion_total = sum(d["duration_seconds"] for d in durations)
    average_completion = (
        completion_total / len(durations) if durations else 0.0
    )

    waits = _task_waits(tasks)
    waiting_total = sum(w["waiting_seconds"] for w in waits)
    average_waiting = waiting_total / len(waits) if waits else 0.0

    return {
        "total_tasks": len(tasks),
        "completed_tasks": len(completed),
        "failed_tasks": len(failed),
        "retried_tasks": len(retried),
        "total_retries": total_retries,
        "total_task_completion_time_seconds": round(completion_total, 6),
        "average_task_completion_time_seconds": round(average_completion, 6),
        "task_completion_durations": durations,
        "total_task_waiting_time_seconds": round(waiting_total, 6),
        "average_task_waiting_time_seconds": round(average_waiting, 6),
        "task_waiting_durations": waits,
        "queue_length_over_time": _queue_series(
            tasks,
            start=timing.get("workflow_started_at"),
            end=timing.get("workflow_completed_at"),
        ),
    }


# -- agent metrics ------------------------------------------------------------


def _active_series(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Number of simultaneously executing agents over time (from task intervals)."""
    deltas: list[tuple[datetime, int]] = []
    for task in tasks:
        if task.get("status") != "COMPLETED":
            continue
        start = _as_utc(task.get("started_at"))
        end = _as_utc(task.get("completed_at"))
        if start is not None and end is not None:
            deltas.append((start, 1))
            deltas.append((end, -1))
    if not deltas:
        return []

    series: list[dict[str, Any]] = []
    current = 0
    previous = 0
    for ts in sorted({t for t, _ in deltas}):
        current += sum(d for t, d in deltas if t == ts)
        if current != previous:
            series.append({"timestamp": ts.isoformat(), "active_agents": current})
            previous = current
    return series


def _utilization_records(
    agents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
    timing: dict[str, Any],
) -> tuple[list[dict[str, Any]], float, float]:
    """Per-agent and aggregate utilization.

    Definitions (documented in docs detail & unit tests):

    * ``active time``        = sum of execution intervals over completed tasks
                              executed by that agent (started_at -> completed_at)
    * ``available time``     = the agent's lifetime within the workflow:
                              baseline agents [workflow_start, workflow_end];
                              dynamically spawned agents [spawn, min(end, terminate)]
    * ``utilization``        = active time / available time
    * ``aggregate``          = total active time across agents / total available time

    Spawned agents are never silently mixed with baseline agents: their
    lifetime is derived from their own spawn/termination events.
    """
    workflow_start = timing.get("workflow_started_at")
    workflow_end = timing.get("workflow_completed_at")

    spawn_times: dict[str, str] = {}
    terminated_times: dict[str, str] = {}
    for event in events:
        if event.get("type") == EventType.AGENT_SPAWNED.value and event.get("agent_id"):
            spawn_times[event["agent_id"]] = event["timestamp"]
        if event.get("type") == EventType.AGENT_TERMINATED.value and event.get("agent_id"):
            terminated_times[event["agent_id"]] = event["timestamp"]

    active_by_agent: dict[str, float] = {}
    for task in tasks:
        if task.get("status") != "COMPLETED":
            continue
        agent_id = task.get("assigned_agent")
        if not agent_id:
            continue
        active_by_agent[agent_id] = (
            active_by_agent.get(agent_id, 0.0)
            + seconds_between(task.get("started_at"), task.get("completed_at"))
        )

    total_active = 0.0
    total_available = 0.0
    records: list[dict[str, Any]] = []
    for agent in agents:
        agent_id = agent["agent_id"]
        active = active_by_agent.get(agent_id, 0.0)
        if agent_id in spawn_times:
            start = spawn_times[agent_id]
            end = terminated_times.get(agent_id, workflow_end)
        else:
            start = workflow_start
            end = workflow_end
        available = seconds_between(start, end)
        utilization = active / available if available > 0 else 0.0
        total_active += active
        total_available += available
        records.append({
            "agent_id": agent_id,
            "role": agent.get("role"),
            "status": agent.get("status"),
            "layout": "dynamic" if agent_id in spawn_times else "baseline",
            "active_seconds": round(active, 6),
            "available_seconds": round(available, 6),
            "utilization": round(min(utilization, 1.0), 6),
        })

    aggregate = total_active / total_available if total_available > 0 else 0.0
    return records, aggregate, total_active


def compute_agent_metrics(
    agents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Agent counts, active series, execution counts, and utilization."""
    completion_counts: Counter = Counter()
    for task in tasks:
        if task.get("status") == "COMPLETED" and task.get("assigned_agent"):
            completion_counts[task["assigned_agent"]] += 1

    spawned = [e for e in events if e.get("type") == EventType.AGENT_SPAWNED.value]
    terminated = [e for e in events if e.get("type") == EventType.AGENT_TERMINATED.value]

    active_series = _active_series(tasks)
    peak_active = max((s["active_agents"] for s in active_series), default=0)

    records, aggregate, total_active = _utilization_records(agents, tasks, events, timing)
    duration = timing.get("duration_seconds", 0.0)
    average_active = total_active / duration if duration > 0 else 0.0

    execution_by_agent = [
        {**record, "execution_count": completion_counts.get(record["agent_id"], 0)}
        for record in records
    ]

    return {
        "initial_agent_count": len(FIXED_AGENT_IDS),
        "active_agent_count": sum(1 for a in agents if a.get("status") == "ACTIVE"),
        "peak_active_agents": peak_active,
        "average_active_agents": round(average_active, 6),
        "agent_utilization": round(aggregate, 6),
        "dynamically_spawned_agents": len(spawned),
        "dynamically_terminated_agents": len(terminated),
        "agents": execution_by_agent,
        "active_agents_over_time": active_series,
    }


# -- adaptive metrics ---------------------------------------------------------


def compute_adaptive_metrics(
    decisions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Decisions, adaptation event counts, and workload/risk series."""
    by_type = Counter(d.get("decision") for d in decisions)
    count_type = lambda name: sum(  # noqa: E731
        1 for e in events if e.get("type") == name
    )
    return {
        "adaptive_decision_count": len(decisions),
        "decisions_by_type": dict(by_type),
        "spawn_events": count_type(EventType.AGENT_SPAWNED.value),
        "termination_events": count_type(EventType.AGENT_TERMINATED.value),
        "reassignment_events": count_type(EventType.TASK_REASSIGNED.value),
        "prioritization_events": count_type(EventType.TASK_PRIORITIZED.value),
        "workload_score_over_time": [
            {"timestamp": d.get("timestamp"), "workload_score": d.get("workload_score")}
            for d in decisions
        ],
        "risk_score_over_time": [
            {"timestamp": d.get("timestamp"), "risk_score": d.get("risk_score")}
            for d in decisions
        ],
    }


# -- communication / tools / quality ------------------------------------------


def compute_communication_metrics(
    communication: list[dict[str, Any]],
) -> dict[str, Any]:
    by_type = Counter(m.get("message_type") for m in communication)
    by_sender = Counter(m.get("sender_agent") for m in communication)
    by_recipient = Counter(m.get("recipient_agent") for m in communication)
    task_related = sum(1 for m in communication if m.get("related_task_id"))
    return {
        "total_messages": len(communication),
        "messages_by_type": dict(by_type),
        "messages_by_sender": dict(by_sender),
        "messages_by_recipient": dict(by_recipient),
        "task_related_messages": task_related,
    }


def compute_tool_metrics(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    by_tool = Counter(t.get("tool_name") for t in tool_calls)
    by_agent = Counter(t.get("agent_id") for t in tool_calls)
    successful = sum(1 for t in tool_calls if t.get("success") is True)
    failed = sum(1 for t in tool_calls if t.get("success") is False)
    total_duration = sum(t.get("duration_ms", 0.0) or 0.0 for t in tool_calls)
    return {
        "total_tool_calls": len(tool_calls),
        "calls_by_tool": dict(by_tool),
        "calls_by_agent": dict(by_agent),
        "successful_calls": successful,
        "failed_calls": failed,
        "total_tool_duration_ms": round(total_duration, 3),
        "average_tool_duration_ms": round(
            total_duration / len(tool_calls), 3
        ) if tool_calls else 0.0,
    }


def compute_quality_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    observations = [
        e for e in events if e.get("type") == EventType.QUALITY_OBSERVATION.value
    ]
    by_category = Counter(o.get("category") for o in observations)
    by_result = Counter(o.get("result") for o in observations)
    return {
        "quality_observation_count": len(observations),
        "observations": observations,
        "counts_by_category": dict(by_category),
        "counts_by_result": dict(by_result),
    }


# -- bundle -------------------------------------------------------------------
COMPUTED_ORDER = ("timing", "task", "agent", "adaptive", "communication", "tools", "quality")


@dataclass
class MetricsBundle:
    """Derived metrics for one run, split by observable category."""

    timing: dict[str, Any] = field(default_factory=dict)
    task: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)
    adaptive: dict[str, Any] = field(default_factory=dict)
    communication: dict[str, Any] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timing": self.timing,
            "task": self.task,
            "agent": self.agent,
            "adaptive": self.adaptive,
            "communication": self.communication,
            "tools": self.tools,
            "quality": self.quality,
        }

    def to_summary(self) -> dict[str, Any]:
        """Flatten scalar metrics into a single JSON-safe summary."""
        summary: dict[str, Any] = {}
        for category in COMPUTED_ORDER:
            data = getattr(self, category)
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    continue
                summary[f"{category}.{key}"] = value
        return summary


def compute_metrics(
    state: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> MetricsBundle:
    """Derive unified metrics from a final state (and its event log).

    The same function is used for fixed, adaptive, and tool-demo runs, which
    guarantees schema parity across strategies.
    """
    events = events if events is not None else state.get("observability_events") or []
    timing = compute_timing(events)
    task = compute_task_metrics(state.get("tasks") or [], timing)
    agent = compute_agent_metrics(
        state.get("agents") or [], state.get("tasks") or [], events, timing
    )
    adaptive = compute_adaptive_metrics(
        state.get("adaptive_decisions") or [], events
    )
    communication = compute_communication_metrics(state.get("communication") or [])
    tools = compute_tool_metrics(state.get("tool_calls") or [])
    quality = compute_quality_metrics(events)
    return MetricsBundle(
        timing=timing,
        task=task,
        agent=agent,
        adaptive=adaptive,
        communication=communication,
        tools=tools,
        quality=quality,
    )


__all__ = [
    "MetricsBundle",
    "compute_agent_metrics",
    "compute_adaptive_metrics",
    "compute_communication_metrics",
    "compute_metrics",
    "compute_quality_metrics",
    "compute_task_metrics",
    "compute_timing",
    "compute_tool_metrics",
]