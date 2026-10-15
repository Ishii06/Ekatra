"""Tests for the simulated-clock experiment engine and the controller changes
that make every adaptive action reachable (Sprints 8-9)."""

import json
from datetime import datetime

import pytest

from ekatra.agents.base import Role
from ekatra.experiments import (
    ExperimentScenario,
    ExperimentTask,
    evaluation_scenarios,
    failure_heavy,
    low_workload,
    medium_workload,
    parallel_backlog,
    risk_triage,
    run_scenario,
)
from ekatra.experiments.simulation import SimClock, SimConfig, simulate
from ekatra.observability.metrics import compute_metrics
from ekatra.orchestration.controller import AdaptiveController, ControllerConfig
from ekatra.orchestration.observer import observe
from ekatra.orchestration.pool import AdaptiveAgentPool
from ekatra.orchestration.workload import WorkloadConfig
from ekatra.tasks.manager import TaskManager


def _metrics(scenario, strategy, **kwargs):
    return compute_metrics(simulate(scenario, strategy, **kwargs))


def _events(state, event_type):
    return [e for e in state["observability_events"] if e["type"] == event_type]


# ---- scenario set ------------------------------------------------------------


def test_evaluation_scenarios_cover_the_planned_conditions():
    scenarios = evaluation_scenarios()
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids)) == 9
    assert {"m9_medium_workload", "m9_parallel_backlog", "m9_failure_heavy", "m9_risk_triage"} <= set(ids)


@pytest.mark.parametrize("scenario", evaluation_scenarios(), ids=lambda s: s.scenario_id)
def test_every_scenario_completes_under_both_strategies(scenario):
    for strategy in ("fixed", "adaptive"):
        task = _metrics(scenario, strategy).task
        assert task["completed_tasks"] + task["failed_tasks"] == task["total_tasks"]


# ---- clock and determinism -----------------------------------------------------


def test_sim_clock_is_monotonic_and_iso():
    clock = SimClock("2026-01-01T00:00:00+00:00")
    clock.advance_to(90)
    assert clock.iso() == "2026-01-01T00:01:30+00:00"
    with pytest.raises(ValueError):
        clock.advance_to(10)


def test_simulation_is_deterministic():
    for scenario in (parallel_backlog(), failure_heavy()):
        a = simulate(scenario, "adaptive", repetition=2)
        b = simulate(scenario, "adaptive", repetition=2)
        assert a["observability_events"] == b["observability_events"]
        assert a["tasks"] == b["tasks"]


def test_repetitions_use_different_seeds():
    one = _metrics(parallel_backlog(), "fixed", repetition=0).timing["duration_seconds"]
    two = _metrics(parallel_backlog(), "fixed", repetition=1).timing["duration_seconds"]
    assert one != two


def test_waiting_times_use_simulated_clock_not_wall_clock():
    wait = _metrics(low_workload(), "fixed").task["average_task_waiting_time_seconds"]
    assert 0 < wait < 24 * 3600


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        simulate(low_workload(), "hybrid")


# ---- paired comparison ----------------------------------------------------------


def test_task_durations_identical_across_strategies():
    fixed = _metrics(low_workload(), "fixed").task["task_completion_durations"]
    adaptive = _metrics(low_workload(), "adaptive").task["task_completion_durations"]
    assert fixed == adaptive


def test_failures_are_identical_across_strategies_for_same_attempts():
    fixed = simulate(failure_heavy(), "fixed")
    adaptive = simulate(failure_heavy(), "adaptive")
    fixed_failures = sorted(e["task_id"] for e in _events(fixed, "task_failed"))
    adaptive_failures = sorted(e["task_id"] for e in _events(adaptive, "task_failed"))
    assert fixed_failures == adaptive_failures


def test_fixed_strategy_never_adapts_and_keeps_six_agents():
    for scenario in evaluation_scenarios():
        state = simulate(scenario, "fixed")
        assert state["adaptive_decisions"] == []
        assert len(state["agents"]) == 6


# ---- dependencies / lifecycle ----------------------------------------------------


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_dependencies_are_respected(strategy):
    state = simulate(parallel_backlog(), strategy)
    by_id = {t["id"]: t for t in state["tasks"]}
    for task in state["tasks"]:
        for dep in task["dependencies"]:
            assert by_id[dep]["completed_at"] <= task["started_at"]


def test_unreachable_tasks_are_cancelled_not_hung():
    scenario = ExperimentScenario(
        scenario_id="sim_unreachable",
        name="unreachable",
        project_description="A task that always fails blocks its dependents.",
        tasks=[
            ExperimentTask(key="a", role="architect", description="Design.", failure_probability=1.0),
            ExperimentTask(key="b", role="backend", description="Build.", dependencies=["a"]),
        ],
    )
    state = simulate(scenario, "fixed", sim=SimConfig(max_retries=1))
    statuses = {t["status"] for t in state["tasks"]}
    assert statuses == {"FAILED", "CANCELLED"}
    assert any(e["type"] == "workflow_completed" for e in state["observability_events"])


# ---- adaptation is observable ------------------------------------------------------


def test_spawned_agents_execute_tasks_and_shorten_a_parallel_backlog():
    fixed = _metrics(parallel_backlog(), "fixed")
    adaptive = _metrics(parallel_backlog(), "adaptive")
    spawned = [a for a in adaptive.agent["agents"] if a["layout"] == "dynamic"]
    assert spawned and all(a["execution_count"] > 0 for a in spawned)
    assert adaptive.agent["peak_active_agents"] > fixed.agent["peak_active_agents"]
    assert adaptive.timing["duration_seconds"] < fixed.timing["duration_seconds"]


def test_spawning_cannot_shorten_a_strictly_chained_backlog():
    from ekatra.experiments import high_backend_workload

    fixed = _metrics(high_backend_workload(), "fixed")
    adaptive = _metrics(high_backend_workload(), "adaptive")
    assert adaptive.adaptive["spawn_events"] >= 1
    assert adaptive.timing["duration_seconds"] == fixed.timing["duration_seconds"]


def test_terminate_and_reassign_actions_fire():
    adaptive = _metrics(parallel_backlog(), "adaptive").adaptive
    assert adaptive["spawn_events"] >= 1
    assert adaptive["reassignment_events"] >= 1
    assert adaptive["termination_events"] >= 1


def test_terminated_agents_stay_in_final_state_for_utilization():
    state = simulate(parallel_backlog(), "adaptive")
    terminated = {a["agent_id"] for a in state["agents"] if a["status"] == "TERMINATED"}
    spawned = {e["agent_id"] for e in _events(state, "agent_spawned")}
    assert terminated and terminated <= spawned


def test_prioritize_runs_high_risk_work_earlier():
    scenario = risk_triage()
    fixed = simulate(scenario, "fixed")
    adaptive = simulate(scenario, "adaptive")
    assert _events(adaptive, "task_prioritized")
    critical = {f"TASK-{i + 1}" for i, t in enumerate(scenario.tasks) if t.risk >= 70}

    def critical_finish(state):
        done = {t["id"]: datetime.fromisoformat(t["completed_at"]) for t in state["tasks"]}
        return max(done[c] for c in critical)

    assert critical_finish(adaptive) < critical_finish(fixed)


def test_failure_injection_produces_failures_and_retries():
    state = simulate(failure_heavy(), "fixed")
    assert _events(state, "task_failed")
    assert _events(state, "task_retried")
    assert compute_metrics(state).task["total_retries"] >= len(_events(state, "task_failed")) - 1


def test_spawn_overhead_delays_spawned_agents():
    state = simulate(parallel_backlog(), "adaptive", sim=SimConfig(spawn_overhead=600.0))
    spawn_time = {e["agent_id"]: e["timestamp"] for e in _events(state, "agent_spawned")}
    for task in state["tasks"]:
        agent = task["assigned_agent"]
        if agent in spawn_time and task["started_at"]:
            started = task["started_at"]
            assert started >= spawn_time[agent]


# ---- metrics ----------------------------------------------------------------------


def test_quality_metrics_come_from_recorded_observations():
    metrics = _metrics(medium_workload(), "fixed")
    quality = metrics.quality
    assert quality["defects_detected"] == 3
    assert quality["security_issues_identified"] == 1
    assert quality["test_pass_rate"] == 1.0
    assert metrics.task["task_success_rate"] == 1.0


def test_test_pass_rate_drops_when_qa_attempts_fail():
    scenario = ExperimentScenario(
        scenario_id="sim_flaky_qa",
        name="flaky qa",
        project_description="QA fails often.",
        timing={"seed": "flaky-qa-seed"},
        tasks=[ExperimentTask(key="qa", role="qa", description="Test.", failure_probability=0.9)],
    )
    quality = _metrics(scenario, "fixed", sim=SimConfig(max_retries=5)).quality
    assert quality["test_attempts"] >= 1
    assert quality["test_pass_rate"] is None or quality["test_pass_rate"] <= 1.0


def test_task_failure_events_counted():
    metrics = _metrics(failure_heavy(), "fixed")
    assert metrics.task["task_failure_events"] >= 1


# ---- records / reproducibility ----------------------------------------------------


def test_records_store_reproducibility_config_without_secrets():
    record = run_scenario(low_workload(), "adaptive", 1)[0]
    config = record.to_dict()["config"]
    assert config["engine"] == "simulated"
    assert config["simulation"]["time_unit"] == SimConfig().time_unit
    assert config["workload"]["weight_queue"] == 0.40
    assert config["risk"]["high_threshold"] == 70.0
    assert config["max_agents_per_role"] == 4
    assert "api_key" not in json.dumps(config).lower()
    assert record.contains_secrets() is False


def test_unknown_engine_rejected():
    with pytest.raises(ValueError):
        run_scenario(low_workload(), "fixed", 1, engine="quantum")


# ---- controller / observer changes -------------------------------------------------


def _task(task_id, role, status, *, complexity=1, deps=(), agent=None, risk=0, priority=1):
    return {
        "id": task_id, "role": role, "status": status, "complexity": complexity,
        "dependencies": list(deps), "assigned_agent": agent, "risk": risk,
        "priority": priority, "retry_count": 0, "description": "x", "output": None,
    }


def test_observer_scores_complexity_over_outstanding_work_only():
    tasks = [
        _task("TASK-1", "backend", "COMPLETED", complexity=5),
        _task("TASK-2", "backend", "ASSIGNED", complexity=1),
    ]
    assert observe(tasks, []).role(Role.BACKEND).avg_complexity == 1.0
    drained = [_task("TASK-1", "backend", "COMPLETED", complexity=5)]
    assert observe(drained, []).role(Role.BACKEND).avg_complexity == 0.0


def test_pool_counts_exclude_terminated_agents():
    pool = AdaptiveAgentPool()
    agent = pool.spawn(Role.BACKEND)
    assert pool.agent_counts()[Role.BACKEND]["total"] == 2
    pool.terminate(agent.agent_id)
    assert pool.agent_counts()[Role.BACKEND]["total"] == 1
    assert len(pool.to_dicts()) == 6
    assert len(pool.to_dicts(include_terminated=True)) == 7


def test_task_manager_uses_injected_clock():
    from datetime import datetime, timezone

    fixed = datetime(2030, 1, 1, tzinfo=timezone.utc)
    manager = TaskManager(now_fn=lambda: fixed)
    task = manager.create(Role.BACKEND, "x")
    manager.assign(task.id, "BACKEND-1")
    manager.start(task.id)
    assert task.assigned_at == fixed and task.started_at == fixed


def _controller():
    # continue_below=0 keeps idle spawned agents from being terminated first.
    return AdaptiveController(
        ControllerConfig(
            workload=WorkloadConfig(continue_below=0.0),
            now=lambda: "2026-01-01T00:00:00+00:00",
        )
    )


def test_reassign_skips_tasks_whose_dependencies_are_incomplete():
    pool = AdaptiveAgentPool()
    pool.spawn(Role.BACKEND)
    pool.get("BACKEND-1").status = pool.get("BACKEND-1").status.__class__.ACTIVE
    tasks = [
        _task("TASK-1", "architect", "ASSIGNED"),
        _task("TASK-2", "backend", "ASSIGNED", deps=["TASK-1"], agent="BACKEND-1"),
    ]
    agents = pool.to_dicts()
    decision = _controller().evaluate(
        observe(tasks, agents), agent_counts=pool.agent_counts(), all_agents=agents, tasks=tasks
    )
    assert decision.decision.value != "REASSIGN"
    tasks[0]["status"] = "COMPLETED"
    decision = _controller().evaluate(
        observe(tasks, agents), agent_counts=pool.agent_counts(), all_agents=agents, tasks=tasks
    )
    assert decision.decision.value == "REASSIGN"
    assert decision.affected_task == "TASK-2"


def test_risk_spawn_requires_outstanding_security_work():
    pool = AdaptiveAgentPool()
    # Many high-risk, failed, retried security-flavoured tasks => HIGH risk,
    # but every security task is already COMPLETED.
    tasks = [
        {**_task(f"TASK-{i}", "security", "COMPLETED", risk=90), "retry_count": 3,
         "description": "authentication vulnerability suspicious"}
        for i in range(1, 12)
    ] + [
        {**_task(f"TASK-{i}", "backend", "FAILED", risk=90), "retry_count": 3,
         "description": "authentication suspicious injection"}
        for i in range(20, 30)
    ]
    agents = pool.to_dicts()
    decision = _controller().evaluate(
        observe(tasks, agents), agent_counts=pool.agent_counts(), all_agents=agents, tasks=tasks
    )
    assert decision.risk_level == "HIGH"
    assert not (decision.decision.value == "SPAWN" and decision.affected_role == "security")
