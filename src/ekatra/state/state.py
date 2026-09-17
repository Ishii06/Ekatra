"""Shared execution state for the Ekatra orchestration workflow.

The state is modeled as a lightweight ``TypedDict`` so that it can be passed
directly through LangGraph nodes while remaining simple to create, extend, and
inspect. This is an architectural choice for this project.

Only the minimal fields needed for the current milestone are defined. Fields
for richer agent/task models will be introduced in later milestones, but the
structure below already covers the surfaces Ekatra will grow into:

* project description
* tasks
* agent information
* current execution information
* messages / agent outputs
* metrics
* adaptive decisions
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class EkatraState(TypedDict, total=False):
    """Shared workflow state threaded through all Ekatra graph nodes.

    All fields are optional so that a minimal state containing nothing more
    than a project description can be created.
    """

    # The initial software project description.
    project_description: str

    # Decomposed development tasks (structured task dicts added later).
    tasks: list[dict[str, Any]]

    # Agent information / active agent pool.
    agents: list[dict[str, Any]]

    # Current execution information.
    current_step: str

    # Messages / agent outputs captured during execution.
    # Accumulates across nodes (appended, never overwritten).
    messages: Annotated[list[str], operator.add]

    # Structured agent-to-agent messages exchanged through the message bus.
    # Accumulates across nodes (appended, never overwritten).
    communication: Annotated[list[dict[str, Any]], operator.add]

    # Measurable execution metrics.
    metrics: dict[str, Any]

    # Recorded adaptive orchestration decisions.
    # Accumulates across nodes (appended, never overwritten).
    adaptive_decisions: Annotated[list[dict[str, Any]], operator.add]

    # Current adaptive cycle number (overwritten each node, not accumulated).
    adaptive_cycle: int

    # Root directory of the tool-assisted execution workspace.
    workspace_root: str

    # Executed tool records (structured ToolResult dicts).
    # Accumulates across nodes (appended, never overwritten).
    tool_calls: Annotated[list[dict[str, Any]], operator.add]

    # Raw observability events recorded during the run (Milestone 7).
    # JSON-safe event dicts; accumulated across nodes (never overwritten).
    observability_events: Annotated[list[dict[str, Any]], operator.add]


def create_initial_state(project_description: str) -> EkatraState:
    """Return a new state initialized from a project description.

    No values in the state depend on a configured API key.
    """
    return EkatraState(
        project_description=project_description,
        tasks=[],
        agents=[],
        current_step="initialized",
        messages=[],
        communication=[],
        metrics={},
        adaptive_decisions=[],
        adaptive_cycle=0,
        workspace_root="",
        tool_calls=[],
        observability_events=[],
    )


__all__ = ["EkatraState", "create_initial_state"]