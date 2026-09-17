"""System observation for the adaptive controller.

``observe`` is a pure, deterministic function that derives a structured
:class:`SystemObservation` from the shared task/agent state. The controller
then consumes this observation to compute workload and risk and to select an
adaptive action.

Derivation assumptions (documented):

* queue length per role: number of the role's tasks that are not COMPLETED or
  CANCELLED (the remaining work of that role)
* complexity per role: average ``complexity`` over the role's tasks
* execution delay per role: fraction of the role's tasks that required a retry
  (the deterministic proxy available in the mock environment)
* failure rate per role: fraction of the role's tasks that are FAILED or RETRY
* global risk indicators: counts of failed tasks / retries, high-risk tasks,
  and keyword/status heuristics over security tasks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ekatra.agents.base import Role
from ekatra.orchestration.risk import RiskConfig, RiskIndicators

# Canonical iteration order used to keep the observation deterministic.
_ROLE_ORDER = (
    Role.PROJECT_MANAGER,
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

_EXECUTABLE = {"PENDING", "ASSIGNED", "RETRY"}
_FAILED_STATES = {"FAILED", "RETRY"}
_TERMINAL = {"COMPLETED", "CANCELLED"}

# Keyword heuristics for risk indicators (experimental and documented).
_SECURITY_FINDING_WORDS = ("finding", "vulnerab")
_AUTH_WORDS = ("auth", "login", "permission", "credential")
_SUSPICIOUS_WORDS = ("suspicious", "malicious", "unsafe", "injection")


@dataclass(frozen=True)
class RoleObservation:
    """Measured per-role execution state used by the workload model."""

    role: Role
    queue_length: int = 0
    running: int = 0
    completed: int = 0
    failed_count: int = 0
    retry_count: int = 0
    avg_complexity: float = 0.0
    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    delay_ratio: float = 0.0
    failure_rate: float = 0.0

    @property
    def has_work(self) -> bool:
        return self.queue_length > 0


@dataclass
class SystemObservation:
    """Full structured observation of the current workflow state."""

    roles: dict[Role, RoleObservation] = field(default_factory=dict)
    indicators: RiskIndicators = field(default_factory=RiskIndicators)

    def role(self, role: Role) -> RoleObservation:
        """Return a role observation, defaulting to an empty one."""
        return self.roles.get(role, RoleObservation(role=role))


def _tasks_by_role(tasks: list[dict[str, Any]]) -> dict[Role, list[dict[str, Any]]]:
    grouped: dict[Role, list[dict[str, Any]]] = {role: [] for role in _ROLE_ORDER}
    for task in tasks:
        role = Role(task["role"])
        grouped.setdefault(role, []).append(task)
    return grouped


def _agents_by_role(agents: list[dict[str, Any]]) -> dict[Role, list[dict[str, Any]]]:
    grouped: dict[Role, list[dict[str, Any]]] = {role: [] for role in _ROLE_ORDER}
    for agent in agents:
        role = Role(agent["role"])
        grouped.setdefault(role, []).append(agent)
    return grouped


def _role_observation(
    role: Role,
    role_tasks: list[dict[str, Any]],
    role_agents: list[dict[str, Any]],
) -> RoleObservation:
    queue_length = sum(1 for t in role_tasks if t["status"] not in _TERMINAL)
    running = sum(1 for t in role_tasks if t["status"] == "RUNNING")
    completed = sum(1 for t in role_tasks if t["status"] == "COMPLETED")
    failed_count = sum(1 for t in role_tasks if t["status"] in _FAILED_STATES)
    retry_count = sum(t.get("retry_count", 0) for t in role_tasks)
    count = len(role_tasks) or 1
    avg_complexity = float(sum(t.get("complexity", 1) for t in role_tasks)) / count

    total_agents = len(role_agents)
    active_agents = sum(1 for a in role_agents if a["status"] == "ACTIVE")
    idle_agents = sum(1 for a in role_agents if a["status"] == "IDLE")

    return RoleObservation(
        role=role,
        queue_length=queue_length,
        running=running,
        completed=completed,
        failed_count=failed_count,
        retry_count=retry_count,
        avg_complexity=avg_complexity,
        total_agents=total_agents,
        active_agents=active_agents,
        idle_agents=idle_agents,
        delay_ratio=min(1.0, retry_count / count),
        failure_rate=min(1.0, failed_count / count),
    )


def _risk_indicators(
    tasks: list[dict[str, Any]],
    risk_config: RiskConfig | None,
) -> RiskIndicators:
    config = risk_config or RiskConfig()
    failed_tasks = [t for t in tasks if t["status"] in _FAILED_STATES]
    security_tasks = [t for t in tasks if t["role"] == Role.SECURITY.value]

    security_findings = 0
    failed_security_checks = 0
    auth_issues = 0
    suspicious_code = 0

    for task in security_tasks:
        output = ((task.get("output") or "") + " " + (task.get("description") or "")).lower()
        if any(word in output for word in _SECURITY_FINDING_WORDS):
            security_findings += 1
        if task["status"] in _FAILED_STATES or task.get("retry_count", 0) > 0:
            failed_security_checks += 1

    for task in failed_tasks:
        text = ((task.get("output") or "") + " " + (task.get("description") or "")).lower()
        if any(word in text for word in _AUTH_WORDS):
            auth_issues += 1
        if any(word in text for word in _SUSPICIOUS_WORDS):
            suspicious_code += 1

    high_risk_tasks = sum(
        1 for t in tasks if t.get("risk", 0) >= config.high_risk_task_threshold
    )
    total_retries = sum(t.get("retry_count", 0) for t in tasks)

    return RiskIndicators(
        security_findings=security_findings,
        failed_security_checks=failed_security_checks,
        auth_issues=auth_issues,
        suspicious_code=suspicious_code,
        task_failures=len(failed_tasks) + total_retries,
        high_risk_tasks=high_risk_tasks,
    )


def observe(
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    risk_config: RiskConfig | None = None,
) -> SystemObservation:
    """Derive a structured observation from task/agent state dicts.

    The observation is fully deterministic: the same state always produces the
    same workload/risk inputs.
    """
    tasks_by_role = _tasks_by_role(tasks)
    agents_by_role = _agents_by_role(agents)

    roles: dict[Role, RoleObservation] = {}
    for role in _ROLE_ORDER:
        roles[role] = _role_observation(
            role,
            tasks_by_role[role],
            agents_by_role[role],
        )

    return SystemObservation(
        roles=roles,
        indicators=_risk_indicators(tasks, risk_config),
    )


__all__ = ["RoleObservation", "SystemObservation", "observe"]