"""Simulated-clock execution for the fixed and adaptive strategies.

Mock agents finish instantly in wall-clock time, so real timings cannot be
compared between strategies. This module runs a scenario on a *virtual* clock
with a small discrete-event scheduler shared by both strategies:

* the fixed baseline never calls the controller (one agent per role, forever);
* the adaptive strategy runs the same deterministic controller used elsewhere
  (observe -> decide -> apply) before work is dispatched at each time point.

Everything except orchestration is identical between strategies. Task
durations and attempt outcomes are derived from a hash of
``(scenario seed, repetition, task key, attempt)`` so a task has the same
duration and the same failures no matter which agent runs it or when. This
makes fixed-vs-adaptive a paired comparison; see ADR-007.

Dispatch rule: a task only runs on the agent it is assigned to. Tasks are
assigned to the role's baseline agent at planning time, so extra capacity is
only used when the controller REASSIGNs work to it - which is what makes the
controller's allocation decisions observable in the results.
"""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ekatra.agents.base import AgentStatus, Role
from ekatra.experiments.scenarios import ExperimentScenario
from ekatra.observability.integration import (
    decision_events,
    quality_observation_event,
    task_assigned_event,
    task_completed_event,
    task_created_event,
    task_failed_event,
    task_reassigned_event,
    task_retried_event,
    task_started_event,
    workflow_completed_event,
    workflow_started_event,
)
from ekatra.orchestration.adaptations import apply_decision
from ekatra.orchestration.controller import AdaptiveController, ControllerConfig
from ekatra.orchestration.decisions import AdaptiveAction
from ekatra.orchestration.observer import observe
from ekatra.orchestration.pool import _BASELINE_IDS, AdaptiveAgentPool
from ekatra.state.state import EkatraState
from ekatra.tasks.manager import TaskManager
from ekatra.tasks.task import TaskStatus

DEFAULT_BASE_TIMESTAMP = "2026-01-01T00:00:00+00:00"
_EXECUTION_ROLES = (Role.ARCHITECT, Role.BACKEND, Role.FRONTEND, Role.QA, Role.SECURITY)
_TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
_MAX_ITERATIONS = 100_000


@dataclass(frozen=True)
class SimConfig:
    """Parameters of the simulated execution environment.

    Attributes:
        time_unit: Simulated seconds of work per unit of task complexity.
        jitter: Relative +/- variation applied to each task's duration.
        spawn_overhead: Seconds before a newly spawned agent can take work.
        max_retries: Retries allowed per task after a failed attempt.
        max_decisions_per_tick: Controller evaluations allowed at one time point.
    """

    time_unit: float = 60.0
    jitter: float = 0.25
    spawn_overhead: float = 30.0
    max_retries: int = 3
    max_decisions_per_tick: int = 8

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unit_interval(*parts: object) -> float:
    """Deterministic float in [0, 1) derived from the hash of ``parts``."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class SimClock:
    """A virtual clock: seconds elapsed since a fixed base timestamp."""

    def __init__(self, base_timestamp: str = DEFAULT_BASE_TIMESTAMP) -> None:
        base = datetime.fromisoformat(base_timestamp)
        self.base = base if base.tzinfo else base.replace(tzinfo=timezone.utc)
        self.t = 0.0

    def advance_to(self, t: float) -> None:
        if t < self.t:
            raise ValueError("simulated time cannot go backwards")
        self.t = t

    def datetime(self) -> datetime:
        return self.base + timedelta(seconds=self.t)

    def iso(self) -> str:
        return self.datetime().isoformat()


@dataclass(order=True)
class _Finish:
    time: float
    seq: int
    task_id: str = field(compare=False)
    agent_id: str = field(compare=False)
    success: bool = field(compare=False)


class _Simulation:
    def __init__(
        self,
        scenario: ExperimentScenario,
        strategy: str,
        repetition: int,
        sim: SimConfig,
        controller_config: ControllerConfig | None,
    ) -> None:
        if strategy not in ("fixed", "adaptive"):
            raise ValueError(f"unknown strategy {strategy!r}; expected 'fixed' or 'adaptive'")
        self.scenario = scenario
        self.strategy = strategy
        self.sim = sim
        self.seed = (scenario.timing or {}).get("seed", scenario.scenario_id)
        self.repetition = repetition
        base = (scenario.timing or {}).get("base_timestamp") or DEFAULT_BASE_TIMESTAMP
        self.clock = SimClock(base)

        self.manager = TaskManager.from_dicts(
            scenario.resolve_tasks(base_timestamp=base), now_fn=self.clock.datetime
        )
        self.defs = {f"TASK-{i + 1}": d for i, d in enumerate(scenario.tasks)}
        self.pool = AdaptiveAgentPool()
        self.available_at: dict[str, float] = {}
        self.finishes: list[_Finish] = []
        self.wakes: list[float] = []  # times a spawned agent becomes available
        self.seq = 0
        self.attempts: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.cycle = 0

        base_cfg = controller_config or ControllerConfig()
        # Decisions are timestamped by the simulated clock, not the wall clock.
        self.controller = AdaptiveController(
            ControllerConfig(
                workload=base_cfg.workload,
                risk=base_cfg.risk,
                max_agents_per_role=base_cfg.max_agents_per_role,
                now=self.clock.iso,
            )
        )

    # -- helpers -------------------------------------------------------------

    def _task(self, task_id: str) -> dict[str, Any]:
        return self.manager.get(task_id).to_dict()

    def _duration(self, task_id: str, attempt: int) -> float:
        task = self.manager.get(task_id)
        key = self.defs[task_id].key
        u = _unit_interval(self.seed, self.repetition, key, attempt, "duration")
        factor = 1.0 + self.sim.jitter * (2.0 * u - 1.0)
        return self.sim.time_unit * task.complexity * factor

    def _attempt_succeeds(self, task_id: str, attempt: int) -> bool:
        p = self.defs[task_id].failure_probability
        if p <= 0.0:
            return True
        key = self.defs[task_id].key
        return _unit_interval(self.seed, self.repetition, key, attempt, "outcome") >= p

    # -- planning ------------------------------------------------------------

    def plan(self) -> None:
        self.events.append(workflow_started_event(self.scenario.project_description, self.clock.iso()))
        for task in self.manager.all():
            self.events.append(task_created_event(task.to_dict()))
        for task in self.manager.all():
            # Work that was already failed when the scenario starts is retried.
            if task.status is TaskStatus.FAILED and task.retry_count < self.sim.max_retries:
                self.manager.retry(task.id)
                self.events.append(task_retried_event(task.to_dict(), self.clock.iso()))
            if task.status in _TERMINAL:
                continue
            self.manager.assign(task.id, _BASELINE_IDS[task.role])
            self.events.append(task_assigned_event(task.to_dict()))

    # -- adaptation ----------------------------------------------------------

    def adapt(self) -> None:
        for _ in range(self.sim.max_decisions_per_tick):
            tasks = self.manager.to_dicts()
            agents = self.pool.to_dicts()
            observation = observe(tasks, agents)
            self.cycle += 1
            decision = self.controller.evaluate(
                observation,
                agent_counts=self.pool.agent_counts(),
                all_agents=agents,
                tasks=tasks,
                cycle=self.cycle,
            )
            apply_decision(decision, self.pool, self.manager)
            record = decision.to_dict()
            self.decisions.append(record)
            self.events.extend(decision_events(record))
            if decision.decision is AdaptiveAction.SPAWN and decision.affected_agent:
                ready_at = self.clock.t + self.sim.spawn_overhead
                self.available_at[decision.affected_agent] = ready_at
                heapq.heappush(self.wakes, ready_at)
            if decision.decision is AdaptiveAction.CONTINUE:
                break

    # -- dispatch ------------------------------------------------------------

    def _repair_assignments(self) -> None:
        """Move work off terminated/unknown agents back to the baseline agent."""
        for task in self.manager.all():
            if task.status not in (TaskStatus.ASSIGNED, TaskStatus.RETRY):
                continue
            try:
                agent = self.pool.get(task.assigned_agent or "")
                alive = agent.status is not AgentStatus.TERMINATED
            except ValueError:
                alive = False
            if not alive:
                target = _BASELINE_IDS[task.role]
                self.events.append(
                    task_reassigned_event(
                        task.id, task.assigned_agent, target,
                        "assigned agent was terminated", self.clock.iso(),
                    )
                )
                task.assigned_agent = target

    def dispatch(self) -> None:
        self._repair_assignments()
        for role in _EXECUTION_ROLES:
            for agent in self.pool.list_agents():
                if agent.role is not role or agent.status is not AgentStatus.IDLE:
                    continue
                if self.available_at.get(agent.agent_id, 0.0) > self.clock.t:
                    continue
                ready = [
                    t for t in self.manager.by_role(role)
                    if t.status in (TaskStatus.ASSIGNED, TaskStatus.RETRY)
                    and t.assigned_agent == agent.agent_id
                    and self.manager.dependencies_satisfied(t)
                ]
                if not ready:
                    continue
                task = min(ready, key=lambda t: (-t.priority, t.id))
                self._start(task.id, agent)

    def _start(self, task_id: str, agent: Any) -> None:
        self.manager.start(task_id)
        attempt = self.attempts.get(task_id, 0) + 1
        self.attempts[task_id] = attempt
        agent.status = AgentStatus.ACTIVE
        agent.current_task = task_id
        self.events.append(task_started_event(self._task(task_id)))
        self.seq += 1
        heapq.heappush(
            self.finishes,
            _Finish(
                time=self.clock.t + self._duration(task_id, attempt),
                seq=self.seq,
                task_id=task_id,
                agent_id=agent.agent_id,
                success=self._attempt_succeeds(task_id, attempt),
            ),
        )

    # -- completion ----------------------------------------------------------

    def finish(self, item: _Finish) -> None:
        agent = self.pool.get(item.agent_id)
        task = self.manager.get(item.task_id)
        definition = self.defs[item.task_id]
        agent.status = AgentStatus.IDLE
        agent.current_task = None
        if item.success:
            result = agent.execute(task)  # deterministic mock output
            agent.status = AgentStatus.IDLE
            self.manager.complete(task.id, output=result.output)
            snapshot = self._task(task.id)
            self.events.append(task_completed_event(snapshot))
            if task.role is Role.QA:
                self.events.append(quality_observation_event("tests", "pass", snapshot))
                if definition.defects:
                    self.events.append(
                        quality_observation_event(
                            "defects_detected", "found", snapshot, count=definition.defects
                        )
                    )
            elif task.role is Role.SECURITY and definition.defects:
                self.events.append(
                    quality_observation_event(
                        "security_issues_identified", "found", snapshot, count=definition.defects
                    )
                )
            return
        self.manager.fail(task.id, reason="simulated attempt failure")
        self.events.append(task_failed_event(self._task(task.id), self.clock.iso()))
        if task.role is Role.QA:
            self.events.append(quality_observation_event("tests", "fail", self._task(task.id), timestamp=self.clock.iso()))
        if task.retry_count < self.sim.max_retries:
            self.manager.retry(task.id)
            self.events.append(task_retried_event(self._task(task.id), self.clock.iso()))

    # -- main loop -----------------------------------------------------------

    def run(self) -> EkatraState:
        self.plan()
        for _ in range(_MAX_ITERATIONS):
            if self.strategy == "adaptive":
                self.adapt()
            self.dispatch()
            while self.wakes and self.wakes[0] <= self.clock.t:
                heapq.heappop(self.wakes)
            if not self.finishes:
                if self.wakes:
                    self.clock.advance_to(heapq.heappop(self.wakes))
                    continue
                self._cancel_unreachable()
                break
            if self.wakes and self.wakes[0] < self.finishes[0].time:
                self.clock.advance_to(heapq.heappop(self.wakes))
                continue
            first = heapq.heappop(self.finishes)
            self.clock.advance_to(first.time)
            batch = [first]
            while self.finishes and self.finishes[0].time <= first.time:
                batch.append(heapq.heappop(self.finishes))
            for item in batch:
                self.finish(item)
        else:  # pragma: no cover - safety net
            raise RuntimeError("simulation did not terminate")
        if self.strategy == "adaptive":
            self.adapt()  # release idle spawned agents now that work has drained
        self.events.append(workflow_completed_event("simulation", self.clock.iso()))
        return self._final_state()

    def _cancel_unreachable(self) -> None:
        """Cancel tasks that can never run (e.g. they depend on a failed task)."""
        for task in self.manager.all():
            if task.status not in _TERMINAL:
                task.status = TaskStatus.CANCELLED

    def _final_state(self) -> EkatraState:
        return {
            "project_description": self.scenario.project_description,
            "tasks": self.manager.to_dicts(),
            "agents": self.pool.to_dicts(include_terminated=True),
            "current_step": "simulation",
            "messages": [],
            "communication": [],
            "metrics": {},
            "adaptive_decisions": self.decisions,
            "adaptive_cycle": self.cycle,
            "observability_events": self.events,
        }


def simulate(
    scenario: ExperimentScenario,
    strategy: str,
    *,
    repetition: int = 0,
    sim: SimConfig | None = None,
    controller_config: ControllerConfig | None = None,
) -> EkatraState:
    """Run ``scenario`` under ``strategy`` on a simulated clock.

    Returns a final workflow state with the same shape the LangGraph workflows
    produce, so ``compute_metrics`` and ``ExperimentRecord`` work unchanged.
    """
    return _Simulation(
        scenario, strategy, repetition, sim or SimConfig(), controller_config
    ).run()


__all__ = ["SimClock", "SimConfig", "simulate"]
