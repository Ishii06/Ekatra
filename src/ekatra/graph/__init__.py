"""Fixed multi-agent workflow for Ekatra.

This milestone wires the fixed baseline organization into a simple
deterministic sequential workflow:

.. code-block:: text

    START
      ↓
    project_manager
      ↓
    architect
      ↓
    backend
      ↓
    frontend
      ↓
    qa
      ↓
    security
      ↓
    END

LangGraph is the workflow/state orchestration technology (ADR-001); it is not
Ekatra's research contribution. There is no dynamic routing, spawning, or
termination in this milestone.
"""

from __future__ import annotations

from typing import Any

from ekatra.graph.nodes import (
    architect_node,
    backend_node,
    frontend_node,
    project_manager_node,
    qa_node,
    security_node,
)
from langgraph.graph import END, START, StateGraph

from ekatra.state.state import EkatraState

GRAPH_NAME = "ekatra_fixed_workflow"


def build_graph():
    """Construct and compile the fixed baseline workflow graph."""
    builder = StateGraph(state_schema=EkatraState)

    builder.add_node("project_manager", project_manager_node)
    builder.add_node("architect", architect_node)
    builder.add_node("backend", backend_node)
    builder.add_node("frontend", frontend_node)
    builder.add_node("qa", qa_node)
    builder.add_node("security", security_node)

    builder.add_edge(START, "project_manager")
    builder.add_edge("project_manager", "architect")
    builder.add_edge("architect", "backend")
    builder.add_edge("backend", "frontend")
    builder.add_edge("frontend", "qa")
    builder.add_edge("qa", "security")
    builder.add_edge("security", END)

    return builder.compile()


def run(initial_state: dict[str, Any] | EkatraState) -> EkatraState:
    """Execute the fixed workflow and return the final state."""
    return build_graph().invoke(initial_state)


__all__ = ["build_graph", "run", "GRAPH_NAME"]