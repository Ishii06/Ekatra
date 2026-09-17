"""Milestone 2 tests: six fixed agents and the fixed multi-agent workflow.

All agent execution is deterministic mock behavior; no LLM API is called.
"""

from __future__ import annotations

import pytest

PROJECT_DESCRIPTION = "Build a simple todo application."


def test_all_six_agent_roles_can_be_instantiated() -> None:
    """Each of the six core agent roles instantiates with a stable identity."""
    from ekatra.agents import ROLES, Role

    assert set(ROLES.keys()) == set(Role)

    for role, cls in ROLES.items():
        agent = cls(agent_id=f"TEST-{role.value.upper()}")
        assert agent.agent_id == f"TEST-{role.value.upper()}"
        assert agent.role is role
        assert agent.status.value == "CREATED"
        assert agent.current_task is None


def test_fixed_pool_contains_exactly_six_expected_agents() -> None:
    """The fixed pool has exactly one instance per role with expected IDs."""
    from ekatra.agents import FIXED_AGENT_IDS, FixedAgentPool, Role

    expected_ids = {
        "PM-1",
        "ARCH-1",
        "FRONTEND-1",
        "BACKEND-1",
        "QA-1",
        "SECURITY-1",
    }

    pool = FixedAgentPool()
    assert len(pool) == 6
    assert set(pool.agent_ids()) == expected_ids

    by_role = {agent.role: agent.agent_id for agent in pool.list_agents()}
    assert by_role == {
        Role.PROJECT_MANAGER: "PM-1",
        Role.ARCHITECT: "ARCH-1",
        Role.FRONTEND: "FRONTEND-1",
        Role.BACKEND: "BACKEND-1",
        Role.QA: "QA-1",
        Role.SECURITY: "SECURITY-1",
    }

    for agent in pool.list_agents():
        assert agent.agent_id == FIXED_AGENT_IDS[agent.role]
        assert agent.status.value == "IDLE"


def test_task_creation_with_required_metadata() -> None:
    """Tasks can be created with all documented metadata fields."""
    from ekatra.agents import Role
    from ekatra.tasks import TaskManager

    manager = TaskManager()
    task = manager.create(
        Role.BACKEND,
        "Implement the API.",
        priority=3,
        complexity=4,
        risk=25,
        dependencies=["TASK-1"],
    )

    assert task.id == "TASK-1"
    assert task.role is Role.BACKEND
    assert task.description == "Implement the API."
    assert task.priority == 3
    assert task.complexity == 4
    assert task.risk == 25
    assert task.dependencies == ["TASK-1"]
    assert task.status.value == "PENDING"
    assert task.assigned_agent is None
    assert task.retry_count == 0
    assert task.created_at is not None
    assert task.started_at is None
    assert task.completed_at is None


def test_agent_executes_task_with_mock_behavior() -> None:
    """An agent receives and executes a task deterministically."""
    from ekatra.agents import QaAgent
    from ekatra.tasks import TaskStatus, TaskManager

    manager = TaskManager()
    task = manager.create("qa", "Run tests for the module.", complexity=2)
    agent = QaAgent(agent_id="QA-1")

    manager.assign(task.id, agent.agent_id)
    task = manager.start(task.id)
    assert task.status is TaskStatus.RUNNING

    result = agent.execute(task)
    assert result.success is True
    assert result.output
    assert result.messages and result.messages[0].startswith("[QA-1]")

    assert agent.status.value == "COMPLETED"
    assert agent.current_task is None
    assert agent.metadata["last_task_id"] == task.id


def test_dependency_rule_blocks_early_start() -> None:
    """A task whose dependencies are incomplete cannot start."""
    from ekatra.agents import Role
    from ekatra.tasks import TaskDependencyError, TaskManager

    manager = TaskManager()
    arch = manager.create(Role.ARCHITECT, "Architecture.")
    frontend = manager.create(
        Role.FRONTEND, "Frontend.", dependencies=[arch.id]
    )
    manager.assign(frontend.id, "FRONTEND-1")

    with pytest.raises(TaskDependencyError):
        manager.start(frontend.id)


def test_fixed_workflow_builds() -> None:
    """The fixed workflow graph compiles successfully."""
    from langgraph.graph.state import CompiledStateGraph

    from ekatra.graph import build_graph

    assert isinstance(build_graph(), CompiledStateGraph)


def test_fixed_workflow_executes_without_api_key() -> None:
    """The workflow runs end-to-end with no API key or LLM calls."""
    from ekatra.config import Settings

    assert Settings().gemini_api_key == ""

    from ekatra.graph import run

    result = run({"project_description": PROJECT_DESCRIPTION})

    assert result["project_description"] == PROJECT_DESCRIPTION
    assert result["current_step"] == "security"


def test_fixed_workflow_state_contains_expected_data() -> None:
    """Final state exposes tasks, agents, assignments, statuses, and messages."""
    from ekatra.agents import FIXED_AGENT_IDS, Role
    from ekatra.graph import run
    from ekatra.state import create_initial_state

    result = run(create_initial_state(PROJECT_DESCRIPTION))

    # --- agents ---
    agents = result["agents"]
    assert len(agents) == 6
    assert {a["agent_id"] for a in agents} == set(FIXED_AGENT_IDS.values())
    completed_agents = {a["agent_id"] for a in agents if a["status"] == "COMPLETED"}
    assert completed_agents == {a for a in FIXED_AGENT_IDS.values()}
    assert all(a["current_task"] is None for a in agents)

    # --- tasks ---
    tasks = result["tasks"]
    assert len(tasks) == 5
    assert {t["role"] for t in tasks} == {
        Role.ARCHITECT.value,
        Role.BACKEND.value,
        Role.FRONTEND.value,
        Role.QA.value,
        Role.SECURITY.value,
    }
    assert all(t["status"] == "COMPLETED" for t in tasks)
    assert all(t["assigned_agent"] is not None for t in tasks)
    assert all(t["output"] for t in tasks)
    assert all(t["started_at"] is not None for t in tasks)
    assert all(t["completed_at"] is not None for t in tasks)

    # assignments match the fixed pool
    assignment = {t["role"]: t["assigned_agent"] for t in tasks}
    assert assignment == {
        Role.ARCHITECT.value: "ARCH-1",
        Role.BACKEND.value: "BACKEND-1",
        Role.FRONTEND.value: "FRONTEND-1",
        Role.QA.value: "QA-1",
        Role.SECURITY.value: "SECURITY-1",
    }

    # development order implies dependency order is respected
    by_role = {t["role"]: t for t in tasks}
    assert by_role[Role.BACKEND.value]["dependencies"] == [
        by_role[Role.ARCHITECT.value]["id"]
    ]
    assert by_role[Role.FRONTEND.value]["dependencies"] == [
        by_role[Role.BACKEND.value]["id"]
    ]

    # --- messages ---
    messages = result["messages"]
    assert messages[0].startswith("[PM-1]")
    for agent_id in ("ARCH-1", "BACKEND-1", "FRONTEND-1", "QA-1", "SECURITY-1"):
        assert any(m.startswith(f"[{agent_id}]") for m in messages)

    # --- metrics ---
    assert result["metrics"]["tasks_created"] == 5
    assert result["metrics"]["tasks_completed"] == 5
    assert result["metrics"]["agents"] == 6
    assert result["metrics"]["strategy"] == "fixed"

    assert result["adaptive_decisions"] == []