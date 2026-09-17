"""State snapshot / serialization helpers.

Produce plain, JSON-safe Python data structures representing the current
task/agent state. These are suitable for logging, experiment records, later
metrics collection, and debugging.

Snapshots contain only execution state (tasks and agents). They never include
configuration, environment values, or secrets such as API keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from ekatra.agents.base import Agent
from ekatra.tasks.task import Task


def _as_task_dict(task: Task | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(task, Task):
        return task.to_dict()
    return dict(task)


def _as_agent_dict(agent: Agent | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(agent, Agent):
        return agent.to_dict()
    return dict(agent)


def create_snapshot(
    tasks: Iterable[Task | Mapping[str, Any]],
    agents: Iterable[Agent | Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Serialize tasks and agents into a deterministic snapshot dict.

    Tasks are ordered by ``id`` and agents by ``agent_id`` so the snapshot is
    stable for logging and experiment records.
    """
    task_list = [_as_task_dict(t) for t in tasks]
    agent_list = [_as_agent_dict(a) for a in agents]
    task_list.sort(key=lambda d: d["id"])
    agent_list.sort(key=lambda d: d["agent_id"])

    timestamp = (generated_at or datetime.now()).isoformat()
    return {
        "generated_at": timestamp,
        "tasks": task_list,
        "agents": agent_list,
    }


def snapshot_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Snapshot the task/agent content of an EkatraState.

    Accepts either a full :class:`~ekatra.state.EkatraState` or any mapping
    exposing ``tasks`` and ``agents`` lists.
    """
    return create_snapshot(state.get("tasks", []), state.get("agents", []))


__all__ = ["create_snapshot", "snapshot_state"]