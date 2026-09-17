"""Fixed agent pool for the baseline organization.

Contains exactly one agent instance per role with deterministic IDs.
"""

from __future__ import annotations

from ekatra.agents.base import Agent, AgentStatus, Role
from ekatra.agents.roles import ROLES

# Deterministic IDs for the fixed baseline (one instance per role).
FIXED_AGENT_IDS: dict[Role, str] = {
    Role.PROJECT_MANAGER: "PM-1",
    Role.ARCHITECT: "ARCH-1",
    Role.FRONTEND: "FRONTEND-1",
    Role.BACKEND: "BACKEND-1",
    Role.QA: "QA-1",
    Role.SECURITY: "SECURITY-1",
}

# Canonical iteration order for the fixed pool.
_POOL_ORDER = (
    Role.PROJECT_MANAGER,
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)


class FixedAgentPool:
    """The fixed multi-agent software engineering organization.

    The pool creates exactly one agent per core role. All agents start
    in ``IDLE`` status, meaning they are available for work.
    """

    def __init__(self, agents: list[Agent] | None = None) -> None:
        if agents is None:
            agents = []
            for role in _POOL_ORDER:
                cls = ROLES[role]
                agent = cls(agent_id=FIXED_AGENT_IDS[role])
                agent.status = AgentStatus.IDLE
                agents.append(agent)
        self._agents: dict[str, Agent] = {a.agent_id: a for a in agents}

    def list_agents(self) -> list[Agent]:
        """Return agents in canonical pool order."""
        return [self._agents[FIXED_AGENT_IDS[r]] for r in _POOL_ORDER if FIXED_AGENT_IDS[r] in self._agents]

    def get(self, agent_id: str) -> Agent:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise ValueError(f"Unknown agent: {agent_id}") from None

    def get_by_role(self, role: Role) -> Agent:
        return self.get(FIXED_AGENT_IDS[role])

    def agent_ids(self) -> list[str]:
        return [a.agent_id for a in self.list_agents()]

    def to_dicts(self) -> list[dict]:
        return [a.to_dict() for a in self.list_agents()]

    @classmethod
    def from_dicts(cls, agent_dicts: list[dict]) -> "FixedAgentPool":
        agents = [Agent.from_dict(d) for d in agent_dicts]
        return cls(agents=agents)

    def __len__(self) -> int:
        return len(self._agents)

    def __repr__(self) -> str:
        ids = ", ".join(self.agent_ids())
        return f"<FixedAgentPool [{ids}]>"


__all__ = ["FixedAgentPool", "FIXED_AGENT_IDS"]