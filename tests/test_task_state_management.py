"""Milestone 3 tests: robust task & state management.

Covers the task lifecycle, invalid transitions, failure/retry, dependency
handling, serialization, agent/task consistency, and state snapshots. No real
LLM API calls are made.
"""

from __future__ import annotations

import json

import pytest

from ekatra.agents import AgentStatus, BackendDeveloperAgent, Role
from ekatra.tasks import TaskDependencyError, TaskManager, TaskStateError, TaskStatus


@pytest.fixture
def manager() -> TaskManager:
    return TaskManager()


def _completed_task(manager: TaskManager) -> str:
    task = manager.create(Role.BACKEND, "Implement the API.")
    manager.assign(task.id, "BACKEND-1")
    manager.start(task.id)
    manager.complete(task.id, output="ok")
    return task.id


# 1. valid lifecycle ---------------------------------------------------------

def test_valid_task_lifecycle(manager: TaskManager) -> None:
    """PENDING -> ASSIGNED -> RUNNING -> COMPLETED."""
    task = manager.create(Role.BACKEND, "Implement the API.")
    assert task.status is TaskStatus.PENDING

    task = manager.assign(task.id, "BACKEND-1")
    assert task.status is TaskStatus.ASSIGNED
    assert task.assigned_agent == "BACKEND-1"

    task = manager.start(task.id)
    assert task.status is TaskStatus.RUNNING
    assert task.started_at is not None

    task = manager.complete(task.id, output="done")
    assert task.status is TaskStatus.COMPLETED
    assert task.completed_at is not None
    assert task.output == "done"


# 2. invalid lifecycle transitions -------------------------------------------

def test_cannot_start_unassigned_task(manager: TaskManager) -> None:
    """An unassigned (PENDING) task cannot start."""
    task = manager.create(Role.BACKEND, "Has no dependencies.")
    with pytest.raises(TaskStateError):
        manager.start(task.id)


def test_cannot_complete_non_running_task(manager: TaskManager) -> None:
    """Only RUNNING tasks can be completed."""
    task = manager.create(Role.BACKEND, "Task.")
    manager.assign(task.id, "BACKEND-1")
    with pytest.raises(TaskStateError):
        manager.complete(task.id)


def test_cannot_assign_completed_task(manager: TaskManager) -> None:
    """A completed task cannot be reassigned."""
    task_id = _completed_task(manager)
    with pytest.raises(TaskStateError):
        manager.assign(task_id, "BACKEND-2")


def test_cannot_retry_non_failed_task(manager: TaskManager) -> None:
    """Only FAILED tasks can be retried."""
    task_id = _completed_task(manager)
    with pytest.raises(TaskStateError):
        manager.retry(task_id)


# 3. failure -> retry lifecycle ----------------------------------------------

def test_failure_to_retry_lifecycle(manager: TaskManager) -> None:
    """RUNNING -> FAILED -> RETRY -> RUNNING -> COMPLETED."""
    task = manager.create(Role.BACKEND, "Implement the endpoint.")
    manager.assign(task.id, "BACKEND-1")
    manager.start(task.id)

    task = manager.fail(task.id, reason="connection refused")
    assert task.status is TaskStatus.FAILED
    assert task.output == "connection refused"
    assert task.completed_at is None

    task = manager.retry(task.id)
    assert task.status is TaskStatus.RETRY
    assert task.retry_count == 1

    task = manager.start(task.id)
    assert task.status is TaskStatus.RUNNING
    assert task.started_at is not None

    task = manager.complete(task.id, output="ok")
    assert task.status is TaskStatus.COMPLETED
    assert task.retry_count == 1


# 4. retry counter -----------------------------------------------------------

def test_retry_counter_increments(manager: TaskManager) -> None:
    """Each retry increments retry_count."""
    task = manager.create(Role.BACKEND, "Flaky task.")
    manager.assign(task.id, "BACKEND-1")

    for expected_count in (1, 2):
        manager.start(task.id)
        manager.fail(task.id, reason="again")
        task = manager.retry(task.id)
        assert task.retry_count == expected_count

    manager.start(task.id)
    manager.complete(task.id, output="finally ok")
    assert task.retry_count == 2


# 5./6./7. dependency handling -----------------------------------------------

def test_dependency_incomplete_blocks_start(manager: TaskManager) -> None:
    """A task cannot start while a dependency is incomplete."""
    arch = manager.create(Role.ARCHITECT, "Architecture.")
    frontend = manager.create(Role.FRONTEND, "Frontend.", dependencies=[arch.id])
    manager.assign(frontend.id, "FRONTEND-1")

    with pytest.raises(TaskDependencyError):
        manager.start(frontend.id)
    assert manager.get(frontend.id).status is TaskStatus.ASSIGNED


def test_dependency_complete_allows_start(manager: TaskManager) -> None:
    """Once all dependencies are completed the task can start."""
    arch = manager.create(Role.ARCHITECT, "Architecture.")
    backend = manager.create(Role.BACKEND, "Backend.", dependencies=[arch.id])
    manager.assign(arch.id, "ARCH-1")
    manager.start(arch.id)
    manager.complete(arch.id, output="arch done")

    manager.assign(backend.id, "BACKEND-1")
    backend = manager.start(backend.id)
    assert backend.status is TaskStatus.RUNNING


def test_missing_dependency_handling(manager: TaskManager) -> None:
    """A task referencing an unknown dependency fails deterministically."""
    frontend = manager.create(Role.FRONTEND, "Frontend.", dependencies=["TASK-99"])
    manager.assign(frontend.id, "FRONTEND-1")

    assert manager.missing_dependencies(frontend) == ["TASK-99"]
    assert manager.dependencies_satisfied(frontend) is False

    with pytest.raises(TaskDependencyError) as excinfo:
        manager.start(frontend.id)
    assert "TASK-99" in str(excinfo.value)


# 8. serialization / restoration ---------------------------------------------

def test_task_serialization_round_trip(manager: TaskManager) -> None:
    """Task and manager state round-trip through plain dicts."""
    from ekatra.tasks import Task

    task_id = _completed_task(manager)
    task = manager.get(task_id)

    restored = Task.from_dict(task.to_dict())
    assert restored == task

    manager2 = TaskManager.from_dicts(manager.to_dicts())
    assert manager2.get(task_id) == task
    assert manager2.all() == manager.all()

    # ID sequencing continues after restoration.
    next_task = manager2.create(Role.SECURITY, "Security review.")
    assert next_task.id == "TASK-2"


def test_manager_status_queries(manager: TaskManager) -> None:
    """Pending/running/completed/failed inspection works."""
    a = manager.create(Role.ARCHITECT, "A.")
    b = manager.create(Role.BACKEND, "B.", dependencies=[a.id])
    manager.assign(a.id, "ARCH-1")
    manager.assign(b.id, "BACKEND-1")

    assert {t.id for t in manager.pending()} == set()
    assert {t.id for t in manager.by_status(TaskStatus.ASSIGNED)} == {a.id, b.id}

    manager.start(a.id)
    manager.complete(a.id, output="ok")
    assert {t.id for t in manager.completed()} == {a.id}
    assert manager.failed() == []
    assert manager.running() == []

    manager.start(b.id)
    manager.fail(b.id, reason="boom")
    assert {t.id for t in manager.failed()} == {b.id}
    assert set(manager.pending()) == set()


# 9. agent/task assignment consistency ---------------------------------------

def test_assignment_keeps_task_and_agent_consistent(manager: TaskManager) -> None:
    """assign() + receive_task() keep task and agent in agreement."""
    agent = BackendDeveloperAgent(agent_id="BACKEND-1")
    task = manager.create(Role.BACKEND, "Implement the API.")

    manager.assign(task.id, agent.agent_id)
    agent.receive_task(task.id)

    assert task.assigned_agent == "BACKEND-1"
    assert agent.current_task == task.id


def test_agent_becomes_active_when_execution_starts(manager: TaskManager) -> None:
    """Agent moves to ACTIVE while a task is being executed."""
    agent = BackendDeveloperAgent(agent_id="BACKEND-1")
    task = manager.create(Role.BACKEND, "Implement the API.")
    manager.assign(task.id, agent.agent_id)
    agent.receive_task(task.id)
    manager.start(task.id)

    seen_statuses: list[AgentStatus] = []

    def spy_run(t: object) -> tuple[str, list[str]]:
        seen_statuses.append(agent.status)
        return "mock output", ["[BACKEND-1] done"]

    agent._run = spy_run  # type: ignore[method-assign]
    result = agent.execute(task)

    assert seen_statuses == [AgentStatus.ACTIVE]
    assert result.success is True


# 10. completed task releases the agent --------------------------------------

def test_completed_task_releases_agent(manager: TaskManager) -> None:
    """On completion the task is COMPLETED and the agent becomes non-active."""
    agent = BackendDeveloperAgent(agent_id="BACKEND-1")
    task = manager.create(Role.BACKEND, "Implement the API.")
    manager.assign(task.id, agent.agent_id)
    agent.receive_task(task.id)
    manager.start(task.id)

    result = agent.execute(task)
    task = manager.complete(task.id, output=result.output)

    assert task.status is TaskStatus.COMPLETED
    assert task.completed_at is not None
    assert task.assigned_agent == "BACKEND-1"
    assert agent.status is AgentStatus.COMPLETED
    assert agent.current_task is None


# 11. state snapshot ---------------------------------------------------------

def test_state_snapshot_serialization() -> None:
    """Snapshots are JSON-safe plain dicts without secrets."""
    from ekatra.agents import FixedAgentPool
    from ekatra.state import create_snapshot
    from ekatra.tasks import TaskManager

    pool = FixedAgentPool()
    tm = TaskManager()
    _completed_task(tm)

    snapshot = create_snapshot(tm.all(), pool.list_agents())

    assert set(snapshot) == {"generated_at", "tasks", "agents"}
    assert isinstance(snapshot["generated_at"], str)
    assert all(isinstance(t, dict) for t in snapshot["tasks"])
    assert all(isinstance(a, dict) for a in snapshot["agents"])
    assert [t["id"] for t in snapshot["tasks"]] == ["TASK-1"]

    # JSON-safe and free of secrets/configuration.
    blob = json.dumps(snapshot)
    lowered = blob.lower()
    assert "api_key" not in lowered
    assert "gemini" not in lowered


def test_snapshot_from_state() -> None:
    """snapshot_state() works on an executed workflow state."""
    from ekatra.graph import run
    from ekatra.state import snapshot_state
    from ekatra.state.state import create_initial_state

    state = run(create_initial_state("Build a todo app."))
    snapshot = snapshot_state(state)

    assert len(snapshot["tasks"]) == 5
    assert len(snapshot["agents"]) == 6
    assert json.dumps(snapshot)  # serializable
    # deterministic ordering
    assert snapshot["tasks"] == sorted(snapshot["tasks"], key=lambda d: d["id"])
    assert snapshot["agents"] == sorted(snapshot["agents"], key=lambda d: d["agent_id"])


# 12. existing fixed workflow still works ------------------------------------

def test_fixed_workflow_still_executes() -> None:
    """The Milestone 2 fixed workflow still runs end-to-end."""
    from ekatra.graph import run
    from ekatra.state.state import create_initial_state

    result = run(create_initial_state("Build a todo application."))

    assert result["current_step"] == "security"
    assert len(result["tasks"]) == 5
    assert all(t["status"] == "COMPLETED" for t in result["tasks"])
    assert len(result["agents"]) == 6
    assert len(result["messages"]) == 6
    assert result["adaptive_decisions"] == []