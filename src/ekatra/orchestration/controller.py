"""Deterministic adaptive controller.

Evaluates the current system observation, computes workload and risk, and
selects exactly one adaptive action following a deterministic priority cascade:

1.  SPAWN  - workload high for a spawnable role under its agent cap
2.  SPAWN  - risk high and security capacity available
3.  TERMINATE  - spawned idle agent under low workload
4.  REASSIGN  - eligible task assigned to a busy agent while idle sibling exists
5.  PRIORITIZE  - high-risk / elevated-risk eligible task below max priority
6.  CONTINUE  - no action required

The controller is the only component authorized to make resource-allocation
decisions. It is fully deterministic and never invokes an LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ekatra.agents.base import Role
from ekatra.orchestration._scoring import clamp100
from ekatra.orchestration.decisions import AdaptiveAction, AdaptiveDecision
from ekatra.orchestration.observer import RoleObservation, SystemObservation
from ekatra.orchestration.pool import SPAWNABLE_ROLES, _BASELINE_IDS
from ekatra.orchestration.risk import RiskConfig, RiskCalculator
from ekatra.orchestration.workload import WorkloadConfig, WorkloadCalculator

# Canonical iteration order for deterministic tie-breaking.
_ROLE_ORDER = (
    Role.PROJECT_MANAGER,
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

_ELIGIBLE = {"PENDING", "ASSIGNED", "FAILED", "RETRY"}


class ControllerConfig:
    """All configurable experimental parameters for the adaptive controller.

    Attributes:
        workload: Workload model configuration.
        risk: Risk model configuration.
        max_agents_per_role: Maximum agents allowed for any spawnable role.
        now: Timestamp factory injected for deterministic tests.
    """

    def __init__(
        self,
        *,
        workload: WorkloadConfig | None = None,
        risk: RiskConfig | None = None,
        max_agents_per_role: int = 4,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.workload = workload or WorkloadConfig()
        self.risk = risk or RiskConfig()
        self.max_agents_per_role = max_agents_per_role
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat())

    def timestamp(self) -> str:
        return self._now()


class AdaptiveController:
    """Stateless, deterministic adaptive orchestration controller."""

    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig()
        self._workload = WorkloadCalculator(self.config.workload)
        self._risk = RiskCalculator(self.config.risk)

    # -- helpers -----------------------------------------------------------

    def _workload_level_for(self, obs: RoleObservation) -> str:
        score = self._workload.score_for(obs)
        return self._workload.level(score)

    def _risk_score(self, indicators: Any) -> float:
        return self._risk.score(indicators)

    def _risk_level(self, score: float) -> str:
        return self._risk.level(score)

    def evaluate(
        self,
        observation: SystemObservation,
        *,
        agent_counts: dict[Role, dict[str, int]] | None = None,
        all_agents: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        cycle: int = 1,
    ) -> AdaptiveDecision:
        """Evaluate the current observation and return exactly one decision.

        ``agent_counts`` is a precomputed per-role summary:
        ``{role: {"total": N, "idle": M, "idle_spawned": I}}``.
        When provided, the controller uses it for the decision logic without
        touching the full agent list. ``all_agents`` and ``tasks`` are used
        only to populate the previous/resulting state snapshots.
        """
        ac = agent_counts or {}
        all_agents = all_agents or []
        tasks = tasks or []

        # -- compute workload scores per role -------------------------------
        workload_scores: dict[str, float] = {}
        for role in _ROLE_ORDER:
            obs = observation.role(role)
            workload_scores[role.value] = round(
                clamp100(self._workload.score_for(obs)), 2
            )

        # -- global risk score -----------------------------------------------
        risk_score = round(clamp100(self._risk_score(observation.indicators)), 2)
        risk_level = self._risk_level(risk_score)

        # -- build previous-state snapshot -----------------------------------
        previous_state = _snapshot(observation, ac, workload_scores, risk_score, risk_level)

        # -- decision cascade ------------------------------------------------
        max_agents = self.config.max_agents_per_role

        # 1. SPAWN (workload high, spawnable role under cap)
        candidate_roles: list[Role] = []
        for role in SPAWNABLE_ROLES:
            ws = workload_scores.get(role.value, 0.0)
            role_info = ac.get(role, {})
            if ws > self.config.workload.monitor_below and role_info.get("total", 0) < max_agents:
                candidate_roles.append(role)

        if candidate_roles:
            best = max(candidate_roles, key=lambda r: workload_scores[r.value])
            new_agent_id = _next_agent_id(best, all_agents)
            return _decision(
                AdaptiveAction.SPAWN,
                workload_scores, risk_score, risk_level, previous_state,
                reason=f"Workload {workload_scores[best.value]:.2f} for {best.value} exceeded spawn threshold {self.config.workload.monitor_below:.0f}",
                affected_role=best.value,
                cycle=cycle, config=self.config,
            )

        # 2. SPAWN security (risk high, security capacity available)
        sec_info = ac.get(Role.SECURITY, {})
        if (
            risk_level == "HIGH"
            and sec_info.get("total", 0) < max_agents
        ):
            return _decision(
                AdaptiveAction.SPAWN,
                workload_scores, risk_score, risk_level, previous_state,
                reason=f"Risk score {risk_score:.2f} exceeded high-risk threshold {self.config.risk.high_threshold:.0f}; allocating security capacity",
                affected_role=Role.SECURITY.value,
                cycle=cycle, config=self.config,
            )

        # 3. TERMINATE (idle spawned agent under low workload)
        for role in SPAWNABLE_ROLES:
            role_info = ac.get(role, {})
            if role_info.get("idle_spawned", 0) > 0 and role_info.get("total", 0) > _baseline_count(role):
                ws = workload_scores.get(role.value, 0.0)
                if ws < self.config.workload.continue_below:
                    term_id = _idle_spawned_id(role, all_agents)
                    return _decision(
                        AdaptiveAction.TERMINATE,
                        workload_scores, risk_score, risk_level, previous_state,
                        reason=f"Idle spawned agent {term_id} under low workload {ws:.2f} (< {self.config.workload.continue_below:.0f})",
                        affected_agent=term_id,
                        cycle=cycle, config=self.config,
                    )

        # 4. REASSIGN (eligible task assigned to non-idle agent; idle sibling exists)
        reassign_result = _reassign_candidate(observation, ac, all_agents, tasks)
        if reassign_result is not None:
            task_info, new_agent = reassign_result
            return _decision(
                AdaptiveAction.REASSIGN,
                workload_scores, risk_score, risk_level, previous_state,
                reason=f"Task {task_info['id']} assigned to busy {task_info.get('assigned_agent')}; idle {new_agent} available",
                affected_task=task_info["id"],
                affected_agent=new_agent,
                cycle=cycle, config=self.config,
            )

        # 5. PRIORITIZE (high-risk / elevated risk, eligible task not max priority)
        prioritize_result = _prioritize_candidate(tasks, risk_level, self.config)
        if prioritize_result is not None:
            task_info, target_priority = prioritize_result
            prev_p = task_info.get("priority", 1)
            return _decision(
                AdaptiveAction.PRIORITIZE,
                workload_scores, risk_score, risk_level, previous_state,
                reason=f"Risk {risk_level} ({risk_score:.2f}); high-risk task {task_info['id']} (risk {task_info.get('risk', 0)}) prioritized to {target_priority}",
                affected_task=task_info["id"],
                cycle=cycle, config=self.config,
                resulting_state_patch={"priority": target_priority},
            )

        # 6. CONTINUE
        return _decision(
            AdaptiveAction.CONTINUE,
            workload_scores, risk_score, risk_level, previous_state,
            reason=f"Conditions within thresholds (workload range [{min(workload_scores.values(), default=0):.2f}-{max(workload_scores.values(), default=0):.2f}], risk {risk_score:.2f})",
            cycle=cycle, config=self.config,
        )


# -- private helpers ---------------------------------------------------------


def _baseline_count(role: Role) -> int:
    """Return how many baseline (non-spawned) agents exist for ``role``.

    There is exactly one fixed-baseline agent per role (see docs/02).
    """
    return 1 if role in _BASELINE_IDS else 0


def _decision(
    action: AdaptiveAction,
    workload_scores: dict[str, float],
    risk_score: float,
    risk_level: str,
    previous_state: dict[str, Any],
    *,
    reason: str,
    affected_role: str | None = None,
    affected_agent: str | None = None,
    affected_task: str | None = None,
    cycle: int = 1,
    config: ControllerConfig,
    resulting_state_patch: dict[str, Any] | None = None,
) -> AdaptiveDecision:
    ws_values = list(workload_scores.values())
    wl = WorkloadCalculator(config.workload).level(max(ws_values) if ws_values else 0.0)
    return AdaptiveDecision(
        timestamp=config.timestamp(),
        cycle=cycle,
        decision=action,
        workload_score=round(max(ws_values) if ws_values else 0.0, 2),
        risk_score=risk_score,
        workload_level=wl,
        risk_level=risk_level,
        reason=reason,
        affected_role=affected_role,
        affected_agent=affected_agent,
        affected_task=affected_task,
        previous_state=previous_state,
        resulting_state=resulting_state_patch or {},
    )


def _snapshot(
    observation: SystemObservation,
    ac: dict[Role, dict[str, int]],
    workload_scores: dict[str, float],
    risk_score: float,
    risk_level: str,
) -> dict[str, Any]:
    queue = {}
    agents = {}
    for role in _ROLE_ORDER:
        obs = observation.role(role)
        info = ac.get(role, {})
        queue[role.value] = obs.queue_length
        agents[role.value] = info.get("total", 0)
    return {
        "queue_length": queue,
        "agents": agents,
        "workload_scores": workload_scores,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "total_agents": sum(info.get("total", 0) for info in ac.values()),
        "spawnable_agents": sum(
            info.get("total", 0)
            for role, info in ac.items()
            if role in SPAWNABLE_ROLES
        ),
    }


def _next_agent_id(role: Role, all_agents: list[dict[str, Any]]) -> str:
    """Determine the next unique agent ID for the given role."""
    role_agents = [a for a in all_agents if a["role"] == role.value]
    max_num = 0
    for agent in role_agents:
        parts = agent["agent_id"].rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            max_num = max(max_num, int(parts[1]))
    return f"{role.value.upper()}-{max_num + 1}"


def _idle_spawned_id(role: Role, all_agents: list[dict[str, Any]]) -> str:
    """Return the agent_id of the first idle spawned agent of this role."""
    baseline = {f"{role.value.upper()}-1"}
    for agent in all_agents:
        if (
            agent["role"] == role.value
            and agent["status"] == "IDLE"
            and agent["agent_id"] not in baseline
        ):
            return agent["agent_id"]
    return ""


def _reassign_candidate(
    observation: SystemObservation,
    ac: dict[Role, dict[str, int]],
    all_agents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    """Return (task_info, target_agent_id) when an idle-agent reassignment exists."""
    for role in _ROLE_ORDER:
        role_info = ac.get(role, {})
        if role_info.get("idle", 0) == 0:
            continue
        role_tasks = [t for t in tasks if t["role"] == role.value and t["status"] in _ELIGIBLE]
        role_agents = {
            a["agent_id"]: a["status"] for a in all_agents if a["role"] == role.value
        }
        idle_agents = [aid for aid, st in role_agents.items() if st == "IDLE"]
        if not idle_agents:
            continue
        for task in sorted(role_tasks, key=lambda t: t["id"]):
            assigned = task.get("assigned_agent")
            if assigned and role_agents.get(assigned) != "IDLE" and assigned in idle_agents:
                continue  # assigned to an idle agent, no reassignment needed
            if assigned and role_agents.get(assigned) != "IDLE":
                target = idle_agents[0]
                return task, target
    return None


def _prioritize_candidate(
    tasks: list[dict[str, Any]],
    risk_level: str,
    config: ControllerConfig,
) -> tuple[dict[str, Any], int] | None:
    """Return (task_info, new_priority) when a task should be elevated."""
    if risk_level not in ("ELEVATED", "HIGH"):
        return None
    threshold = config.risk.high_risk_task_threshold
    candidates = [
        t for t in tasks
        if t["status"] in _ELIGIBLE and t.get("risk", 0) >= threshold and t.get("priority", 1) < 3
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda t: (t["priority"], t["id"]))
    return best, min(3, best["priority"] + 1)


__all__ = ["AdaptiveController", "ControllerConfig", "SPAWNABLE_ROLES"]