"""Milestone 8: scenario model for the deterministic experiment harness.

A scenario is a single shared input that is handed to both orchestration
strategies unchanged: a project description plus a constrained task set, a
small timing/seed metadata block, and a record of the characteristics the
scenario is designed to exhibit. Martens: no secrets, no environment values,
no absolute paths, no credentials are allowed by construction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ekatra.agents.base import Role
from ekatra.tasks.manager import TaskManager
from ekatra.tasks.task import TaskStatus

_EXECUTION_ROLES = (
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

_SECRET_VALUE_MARKERS = (
    "sk-",
    "api_key=",
    "apikey",
    "bearer ",
    "-----begin",
    "gemini_api_key",
    "password=",
    "secret=",
    "token=",
    "credential=",
)
_SECRET_WHOLE_WORDS = {"password", "passphrase", "a0c0b"}


def _has_secret(text: str) -> bool:
    """Best-effort heuristic guarding against API keys/credentials in scenarios.

    Flags obvious key/value payloads and credential-naming words, while plain
    nouns such as "credential", "permission", or "authentication" in a security
    review's task wording remain valid.
    """
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_VALUE_MARKERS):
        return True
    tokens = {part.strip(".,;:()[]{}!?\"'") for part in lowered.split() if part.strip(".,;:()[]{}!?\"'")}
    return bool(tokens & _SECRET_WHOLE_WORDS)


class ExperimentTask(BaseModel):
    """One declared task inside a scenario, independent of any TaskManager."""

    key: str
    role: Role
    description: str
    priority: int = Field(default=1, ge=1, le=3)
    complexity: int = Field(default=1, ge=1, le=5)
    risk: int = Field(default=0, ge=0, le=100)
    dependencies: list[str] = Field(default_factory=list)
    initial_status: TaskStatus | None = None
    retry_count: int = Field(default=0, ge=0)

    @field_validator("key")
    @classmethod
    def _key_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task key must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task description must not be blank")
        return value.strip()

    @field_validator("description")
    @classmethod
    def _description_disallows_paths(cls, value: str) -> str:
        if "\\" in value or value.strip().startswith("/"):
            raise ValueError("task descriptions must not contain paths")
        return value.strip()

    @field_validator("description")
    @classmethod
    def _description_disallows_secrets(cls, value: str) -> str:
        if _has_secret(value):
            raise ValueError("task descriptions must not contain secrets or credentials")
        return value.strip()


class ExperimentScenario(BaseModel):
    """A shared, serializable experiment input for both strategies."""

    scenario_id: str
    name: str
    description: str = ""
    project_description: str
    tasks: list[ExperimentTask] = Field(min_length=1)
    timing: dict[str, Any] = Field(default_factory=dict)
    expected_characteristics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_id")
    @classmethod
    def _id_valid(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("scenario_id must be at least 3 characters")
        return cleaned

    @field_validator("project_description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_description must not be blank")
        return value.strip()

    @field_validator("project_description")
    @classmethod
    def _description_disallows_secrets(cls, value: str) -> str:
        if _has_secret(value):
            raise ValueError("project_description must not contain secrets or credentials")
        return value.strip()

    @model_validator(mode="after")
    def _validate_task_set(self) -> "ExperimentScenario":
        keys = [task.key for task in self.tasks]
        if len(keys) != len(set(keys)):
            raise ValueError("task keys must be unique within a scenario")
        allowed = {role.value for role in _EXECUTION_ROLES}
        declared = {task.role.value for task in self.tasks}
        forbidden = declared - allowed
        if forbidden:
            raise ValueError(f"tasks must use one of {sorted(allowed)}, got {sorted(forbidden)}")
        known = set()
        for task in self.tasks:
            unknown = [dep for dep in task.dependencies if dep not in known]
            if unknown:
                raise ValueError(
                    f"task {task.key!r} depends on unknown or out-of-order keys {unknown}"
                )
            known.add(task.key)
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentScenario":
        return cls.model_validate(data)

    def resolve_tasks(self, base_timestamp: str | None = None) -> list[dict[str, Any]]:
        """Build deterministic task-state dicts from the declared task set.

        Tasks receive sequential ``TASK-N`` ids in declaration order and the
        declared dependency keys are resolved to those ids. Task state then
        flows to the workflows exactly as stored (``initial_status`` and
        ``retry_count`` reproduce e.g. already-failed or retried work).
        """
        manager = TaskManager()
        id_by_key: dict[str, str] = {}
        by_id: dict[str, Any] = {}
        for definition in self.tasks:
            task = manager.create(
                role=definition.role,
                description=definition.description,
                priority=definition.priority,
                complexity=definition.complexity,
                risk=definition.risk,
            )
            id_by_key[definition.key] = task.id
            by_id[task.id] = task
        for definition in self.tasks:
            task = by_id[id_by_key[definition.key]]
            task.dependencies = [id_by_key[dep] for dep in definition.dependencies]
            if definition.initial_status is not None:
                task.status = definition.initial_status
            task.retry_count = definition.retry_count
        if base_timestamp:
            base = datetime.fromisoformat(base_timestamp)
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            for task in by_id.values():
                task.created_at = base
        return manager.to_dicts()