"""Deterministic task management.

Owns task creation, lifecycle transitions, and dependency checks. This is the
Task Manager component described in ``docs/02-system-architecture.md`` and
``docs/05-task-state-model.md``; it remains fully deterministic.

Lifecycle rules enforced by this manager:

* ``PENDING -> ASSIGNED -> RUNNING -> COMPLETED``
* failure path: ``RUNNING -> FAILED -> RETRY -> RUNNING``
* a task may only start when it is assigned (or being retried) and all of its
  dependencies are completed
* ``retry`` increments ``retry_count`` and is only valid for FAILED tasks

Invalid transitions raise :class:`TaskStateError`; dependency problems raise
:class:`TaskDependencyError`. All checks are deterministic.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ekatra.agents.base import Role
from ekatra.tasks.task import Task, TaskStatus

_ID_PATTERN = re.compile(r"^TASK-(\d+)$")

# Statuses from which an assignment is permissible.
_ASSIGNABLE = {
    TaskStatus.PENDING,
    TaskStatus.ASSIGNED,
    TaskStatus.FAILED,
    TaskStatus.RETRY,
}
# Statuses from which a task may (re)start execution.
_STARTABLE = {TaskStatus.ASSIGNED, TaskStatus.RETRY}


class TaskError(RuntimeError):
    """Base error for invalid task operations."""


class TaskStateError(TaskError):
    """Raised when a task transition is not valid for its current state."""


class TaskDependencyError(TaskError):
    """Raised when a task is started before its dependencies are complete."""


class TaskManager:
    """Creates tasks and controls their lifecycle transitions.

    The manager is rebuilt from the shared state whenever a graph node needs
    it, keeping the shared ``EkatraState["tasks"]`` list authoritative.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._next_number = 1

    # -- construction ------------------------------------------------------

    def create(
        self,
        role: Role,
        description: str,
        *,
        priority: int = 1,
        complexity: int = 1,
        risk: int = 0,
        dependencies: list[str] | None = None,
    ) -> Task:
        """Create a PENDING task with the next sequential ID."""
        task = Task(
            id=f"TASK-{self._next_number}",
            role=role,
            description=description,
            priority=priority,
            complexity=complexity,
            risk=risk,
            dependencies=list(dependencies or []),
        )
        self._tasks[task.id] = task
        self._next_number += 1
        return task

    @classmethod
    def from_dicts(cls, task_dicts: list[dict[str, Any]]) -> "TaskManager":
        """Rebuild a manager from state task dicts."""
        manager = cls()
        manager._tasks = {t["id"]: Task.from_dict(t) for t in task_dicts}
        numbers = (_ID_PATTERN.match(tid) for tid in manager._tasks)
        existing = [int(m.group(1)) for m in numbers if m]
        manager._next_number = (max(existing) + 1) if existing else 1
        return manager

    # -- queries -----------------------------------------------------------

    def get(self, task_id: str) -> Task | None:
        """Retrieve a task by ID, or None when unknown."""
        return self._tasks.get(task_id)

    def all(self) -> list[Task]:
        """All tasks in creation order."""
        return list(self._tasks.values())

    def by_role(self, role: Role) -> list[Task]:
        """Tasks assigned to the given role."""
        return [t for t in self._tasks.values() if t.role == role]

    def by_status(self, status: TaskStatus) -> list[Task]:
        """Tasks currently in the given lifecycle status."""
        return [t for t in self._tasks.values() if t.status is status]

    def pending(self) -> list[Task]:
        return self.by_status(TaskStatus.PENDING)

    def running(self) -> list[Task]:
        return self.by_status(TaskStatus.RUNNING)

    def completed(self) -> list[Task]:
        return self.by_status(TaskStatus.COMPLETED)

    def failed(self) -> list[Task]:
        return self.by_status(TaskStatus.FAILED)

    # -- dependency validation ----------------------------------------------

    def missing_dependencies(self, task: Task) -> list[str]:
        """Dependency IDs referenced by the task but unknown to the manager."""
        return [dep for dep in task.dependencies if dep not in self._tasks]

    def incomplete_dependencies(self, task: Task) -> list[str]:
        """Dependency IDs that exist but are not yet COMPLETED."""
        return [
            dep
            for dep in task.dependencies
            if dep in self._tasks and self._tasks[dep].status is not TaskStatus.COMPLETED
        ]

    def dependencies_satisfied(self, task: Task) -> bool:
        """A task is executable only when all dependencies are complete."""
        return not (self.missing_dependencies(task) or self.incomplete_dependencies(task))

    def validate_dependencies(self, task: Task) -> None:
        """Raise TaskDependencyError when dependencies are missing/incomplete."""
        missing = self.missing_dependencies(task)
        if missing:
            raise TaskDependencyError(
                f"Task {task.id} references unknown dependencies: {missing}"
            )
        incomplete = self.incomplete_dependencies(task)
        if incomplete:
            raise TaskDependencyError(
                f"Task {task.id} has incomplete dependencies: {incomplete}"
            )

    # -- lifecycle transitions ---------------------------------------------

    def assign(self, task_id: str, agent_id: str) -> Task:
        """Assign a task to an agent.

        Allowed for PENDING, ASSIGNED, FAILED, and RETRY tasks. A PENDING task
        becomes ASSIGNED; other statuses keep their state while the assigned
        agent is updated. Completed and running tasks cannot be reassigned.
        """
        task = self._require(task_id)
        if task.status not in _ASSIGNABLE:
            raise TaskStateError(
                f"Task {task_id} cannot be assigned from status {task.status.value}"
            )
        task.assigned_agent = agent_id
        if task.assigned_at is None:
            task.assigned_at = datetime.now(timezone.utc)
        if task.status is TaskStatus.PENDING:
            task.status = TaskStatus.ASSIGNED
        return task

    def start(self, task_id: str) -> Task:
        """Start (or restart) a task once assigned and dependencies are met.

        Allowed from ASSIGNED or RETRY. PENDING (unassigned) tasks cannot
        start. ``started_at`` is recorded for the current attempt.
        """
        task = self._require(task_id)
        if task.status not in _STARTABLE:
            raise TaskStateError(
                f"Task {task_id} cannot start from status {task.status.value}"
            )
        self.validate_dependencies(task)
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        return task

    def complete(self, task_id: str, output: str | None = None) -> Task:
        """Mark a running task COMPLETED and record its output."""
        task = self._require(task_id)
        if task.status is not TaskStatus.RUNNING:
            raise TaskStateError(
                f"Task {task_id} cannot complete from status {task.status.value}"
            )
        task.status = TaskStatus.COMPLETED
        task.output = output
        if task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        return task

    def fail(self, task_id: str, reason: str | None = None) -> Task:
        """Mark a running task FAILED, optionally recording the failure reason."""
        task = self._require(task_id)
        if task.status is not TaskStatus.RUNNING:
            raise TaskStateError(
                f"Task {task_id} cannot fail from status {task.status.value}"
            )
        task.status = TaskStatus.FAILED
        task.completed_at = None
        if reason is not None:
            task.output = reason
        return task

    def retry(self, task_id: str) -> Task:
        """Mark a FAILED task for retry and increment ``retry_count``.

        Only FAILED tasks may be retried. The resulting RETRY task can be
        restarted through :meth:`start`.
        """
        task = self._require(task_id)
        if task.status is not TaskStatus.FAILED:
            raise TaskStateError(
                f"Task {task_id} cannot retry from status {task.status.value}"
            )
        task.status = TaskStatus.RETRY
        task.retry_count += 1
        return task

    def set_priority(
        self, task_id: str, priority: int, reason: str = ""
    ) -> Task:
        """Update a task's priority and record the change in priority_history.

        Raises:
            ValueError: If the priority is not between 1 and 3.
            TaskError: If the task is unknown.
        """
        if priority < 1 or priority > 3:
            raise ValueError(f"Priority must be between 1 and 3, got {priority}")
        task = self._require(task_id)
        previous = task.priority
        if previous == priority:
            return task
        task.priority = priority
        task.priority_history.append({
            "priority": priority,
            "previous_priority": previous,
            "reason": reason,
        })
        return task

    # -- serialization -----------------------------------------------------

    def to_dicts(self) -> list[dict[str, Any]]:
        """Serialize all tasks in creation order to state-compatible dicts."""
        return [t.to_dict() for t in self.all()]

    def _require(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskError(f"Unknown task: {task_id}")
        return task


__all__ = [
    "TaskManager",
    "TaskError",
    "TaskStateError",
    "TaskDependencyError",
]