"""Foundation tests for the Ekatra project skeleton.

These tests must never require a real LLM API call: they only exercise
imports, configuration loading, state creation, and the LangGraph workflow.
"""

from __future__ import annotations

import pytest

PROJECT_DESCRIPTION = "Build a simple todo application."


def test_project_imports() -> None:
    """The ekatra package and its core subpackages import successfully."""
    import ekatra  # noqa: F401

    from ekatra.config import Settings, get_settings  # noqa: F401
    from ekatra.graph import build_graph, run  # noqa: F401
    from ekatra.state import EkatraState, create_initial_state  # noqa: F401


def test_config_loads_without_api_key() -> None:
    """Settings load successfully even when no API key is configured."""
    from ekatra.config import Settings

    settings = Settings()
    assert settings.llm_provider == "gemini"
    assert settings.gemini_api_key == ""
    assert settings.has_api_key() is False


def test_state_can_be_created() -> None:
    """An initial EkatraState can be created from a project description."""
    from ekatra.state import EkatraState, create_initial_state

    state = create_initial_state(PROJECT_DESCRIPTION)
    assert isinstance(state, dict)
    assert state["project_description"] == PROJECT_DESCRIPTION
    assert state["current_step"] == "initialized"
    assert state["tasks"] == []
    assert state["agents"] == []
    assert state["messages"] == []
    assert state["metrics"] == {}
    assert state["adaptive_decisions"] == []

    # Keys present match the EkatraState schema.
    assert set(state.keys()) == EkatraState.__annotations__.keys()


def test_graph_can_be_constructed() -> None:
    """The minimal workflow builds into a compilable LangGraph."""
    from langgraph.graph.state import CompiledStateGraph

    from ekatra.graph import build_graph

    graph = build_graph()
    assert isinstance(graph, CompiledStateGraph)


def test_graph_executes_with_expected_state() -> None:
    """The graph runs on a simple input and returns the expected fields."""
    from ekatra.graph import build_graph
    from ekatra.state import EkatraState, create_initial_state

    result = build_graph().invoke(create_initial_state(PROJECT_DESCRIPTION))

    assert isinstance(result, dict)
    assert set(result.keys()) == EkatraState.__annotations__.keys()

    assert result["project_description"] == PROJECT_DESCRIPTION
    assert result["current_step"] == "security"
    assert len(result["messages"]) >= 6
    assert result["messages"][0].startswith("[PM-1]")
    assert len(result["tasks"]) == 5
    assert len(result["agents"]) == 6
    assert result["metrics"]
    assert result["adaptive_decisions"] == []


def test_run_helper_executes_workflow() -> None:
    """The run() convenience helper returns a valid final state."""
    from ekatra.graph import run

    result = run({"project_description": PROJECT_DESCRIPTION})

    assert result["project_description"] == PROJECT_DESCRIPTION
    assert result["current_step"] == "security"
    assert len(result["messages"]) >= 6