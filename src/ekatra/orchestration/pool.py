"""Dynamic, spawnable agent pool for the adaptive workflow.

Extends the baseline agent organization with runtime ``spawn`` and
``terminate`` capabilities. The original fixed-baseline agents are protected:
they cannot be removed by adaptive cleanup.

Agents follow the lifecycle ``CREATED → IDLE → ACTIVE → COMPLETED → IDLE``
(``docs/05-task-state-model.md``); terminated agents are marked TERMINATED but
kept for serialization and observability.
"""

from __future__ import annotations

import re
from typing import Any

from ekatra.agents.base import Agent, AgentStatus, Role
from ekatra.agents.roles import ROLES

# Canonical iteration order for deterministic snapshots.
_POOL_ORDER = (
    Role.PROJECT_MANAGER,
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

_BASELINE_IDS: dict[Role, str] = {
    Role.PROJECT_MANAGER: "PM-1",
    Role.ARCHITECT: "ARCH-1",
    Role.FRONTEND: "FRONTEND-1",
    Role.BACKEND: "BACKEND-1",
    Role.QA: "QA-1",
    Role.SECURITY: "SECURITY-1",
}

# Roles eligible for dynamic scaling (from docs/02, docs/03, docs/04).
SPAWNABLE_ROLES = (Role.BACKEND, Role.FRONTEND, Role.QA, Role.SECURITY)

_ID_PATTERN = re.compile(r"^(.+)-(\d+)$")


def _is_baseline(agent_id: str) -> bool:
    return agent_id in _BASELINE_IDS.values()


def _extract_number(agent_id: str) -> tuple[str, int]:
    match = _ID_PATTERN.match(agent_id)
    if match:
        return match.group(1), int(match.group(2))
    return agent_id, 0


class AdaptiveAgentPool:
    """Dynamic agent pool that can scale roles at runtime.

    Starts with the fixed six-agent baseline and supports ``spawn`` /
    ``terminate`` operations for eligible roles.
    """

    def __init__(self, agents: list[Agent] | None = None) -> None:
        if agents is None:
            agents = []
            for role in _POOL_ORDER:
                cls = ROLES[role]
                agent = cls(agent_id=_BASELINE_IDS[role])
                agent.status = AgentStatus.IDLE
                agents.append(agent)
        self._agents: dict[str, Agent] = {a.agent_id: a for a in agents}

    # -- queries -----------------------------------------------------------

    def list_agents(self) -> list[Agent]:
        """Return all non-terminated agents in canonical + creation order."""
        order = []
        baseline_order = {role: i for i, role in enumerate(_POOL_ORDER)}
        non_terminated = [a for a in self._agents.values() if a.status is not AgentStatus.TERMINATED]

        def sort_key(agent: Agent) -> tuple[int, int]:
            role_idx = baseline_order.get(Role(agent.role), 999)
            is_base = _is_baseline(agent.agent_id)
            return (0 if is_base else 1, role_idx)

        return sorted(non_terminated, key=sort_key)

    def get(self, agent_id: str) -> Agent:
        if agent_id not in self._agents:
            raise ValueError(f"Unknown agent: {agent_id}")
        return self._agents[agent_id]

    def get_by_role(self, role: Role) -> Agent:
        for agent in self._agents.values():
            if agent.role is role and agent.status is not AgentStatus.TERMINATED:
                return agent
        raise ValueError(f"No available agent for role {role.value}")

    def available_for(self, role: Role) -> list[Agent]:
        """Return idle, non-terminated agents of the given role."""
        return [
            a
            for a in self._agents.values()
            if a.role is role and a.status is AgentStatus.IDLE
        ]

    def agent_ids(self) -> list[str]:
        return [a.agent_id for a in self.list_agents()]

    def count_by_role(self) -> dict[Role, int]:
        counts: dict[Role, int] = {role: 0 for role in _POOL_ORDER}
        for agent in self.list_agents():
            role = Role(agent.role)
            counts[role] = counts.get(role, 0) + 1
        return counts

    def agent_counts(self) -> dict[Role, dict[str, int]]:
        """Per-role summary: total, idle, idle_spawned, active, terminated."""
        counts: dict[Role, dict[str, int]] = {}
        for role in _POOL_ORDER:
            counts[role] = {"total": 0, "idle": 0, "idle_spawned": 0, "active": 0}
        for agent in self._agents.values():
            role = Role(agent.role)
            info = counts.setdefault(role, {"total": 0, "idle": 0, "idle_spawned": 0, "active": 0})
            info["total"] += 1
            if agent.status is AgentStatus.IDLE:
                info["idle"] += 1
                if not _is_baseline(agent.agent_id):
                    info["idle_spawned"] += 1
            elif agent.status is AgentStatus.ACTIVE:
                info["active"] += 1
        return counts

    def to_dicts(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self.list_agents()]

    @classmethod
    def from_dicts(cls, agent_dicts: list[dict[str, Any]]) -> "AdaptiveAgentPool":
        agents = [Agent.from_dict(d) for d in agent_dicts]
        return cls(agents=agents)

    # -- spawn / terminate -------------------------------------------------

    def spawn(self, role: Role) -> Agent:
        """Create a new idle agent of the given role with a unique ID.

        Only roles in ``SPAWNABLE_ROLES`` may be scaled dynamically.
        """
        if role not in SPAWNABLE_ROLES:
            raise ValueError(f"Role {role.value} is not spawnable")
        agent_id = self._next_agent_id(role)
        cls = ROLES[role]
        agent = cls(agent_id=agent_id)
        agent.status = AgentStatus.IDLE
        self._agents[agent_id] = agent
        return agent

    def terminate(self, agent_id: str) -> Agent:
        """Safely remove a dynamically spawned agent.

        Raises:
            ValueError: If the agent is a baseline agent or is ACTIVE.
        """
        if agent_id not in self._agents:
            raise ValueError(f"Unknown agent: {agent_id}")
        agent = self._agents[agent_id]
        if _is_baseline(agent_id):
            raise ValueError(f"Cannot terminate baseline agent {agent_id}")
        if agent.status is AgentStatus.ACTIVE:
            raise ValueError(f"Cannot terminate active agent {agent_id}")
        agent.status = AgentStatus.TERMINATED
        return agent

    def __len__(self) -> int:
        return len(self._agents)

    def __repr__(self) -> str:
        ids = ", ".join(self.agent_ids())
        return f"<AdaptiveAgentPool [{ids}]>"

    # -- internal ----------------------------------------------------------

    def _next_agent_id(self, role: Role) -> str:
        prefix = role.value.upper()
        max_num = 0
        for agent_id in self._agents:
            p, num = _extract_number(agent_id)
            if p == prefix and num > max_num:
                max_num = num
        return f"{prefix}-{max_num + 1}"


__all__ = [
    "AdaptiveAgentPool",
    "SPAWNABLE_ROLES",
    "_BASELINE_IDS",
    "_is_baseline",
]