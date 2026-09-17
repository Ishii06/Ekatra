"""Milestone 8 tests: scenario model, fixtures, and experiment runner.

The harness is descriptive and deterministic. These tests verify that a
scenario is a single shared input, that the runner rebuilds identical task sets
for both strategies, that runs terminate within the adaptive round limit, and
that every produced record is complete, JSON-serializable, secret-free, and
aligned with the M7 schema.
"""

from __future__ import annotations

import json

import pytest

import ekatra.config.settings as settings_module
from ekatra.config.settings import Settings
from ekatra.experiments.fixtures import (
    all_scenarios,
    high_backend_workload,
    high_frontend_workload,
    low_workload,
    mixed_high_workload,
    security_risk,
)
from ekatra.experiments.runner import (
    build_initial_state,
    run_all_scenarios,
    run_comparison,
    run_scenario,
)
from ekatra.experiments.scenarios import (
    ExperimentScenario,
    ExperimentTask,
)
from ekatra.graph.adaptive import run_adaptive
from ekatra.observability.integration import (
    ADAPTIVE_ONLY_TYPES,
    finalize_workflow_events,
    workflow_reached_terminal_state,
)
from ekatra.tasks.task import TaskStatus


# ---- Scenario model ----------------------------------------------------------


class TestExperimentScenarioModel:
    def test_scenario_roundtrip_preserves_fields(self):
        scenario = low_workload()
        data = scenario.to_dict()
        restored = ExperimentScenario.from_dict(data)
        assert restored == scenario
        assert restored.scenario_id == scenario.scenario_id
        assert restored.project_description == scenario.project_description
        assert [task.key for task in restored.tasks] == [task.key for task in scenario.tasks]
        assert data["timing"]["seed"] == "ekatra-m8-low"

    def test_task_keys_must_be_unique(self):
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_dup",
                name="dup",
                project_description="dup project",
                tasks=[
                    ExperimentTask(key="a", role="backend", description="one"),
                    ExperimentTask(key="a", role="frontend", description="two"),
                ],
            )

    def test_dependencies_must_be_ordered(self):
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_ordering",
                name="ordering",
                project_description="ordering project",
                tasks=[
                    ExperimentTask(
                        key="second", role="frontend", description="two", dependencies=["first"]
                    ),
                    ExperimentTask(key="first", role="backend", description="one"),
                ],
            )

    def test_project_manager_role_forbidden(self):
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_roles",
                name="roles",
                project_description="roles project",
                tasks=[
                    ExperimentTask(
                        key="pm", role="project_manager", description="plan only"
                    ),
                ],
            )

    def test_blank_project_description_rejected(self):
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_blank",
                name="blank",
                project_description="  ",
                tasks=[ExperimentTask(key="a", role="backend", description="one")],
            )

    def test_scenarios_allow_plain_security_terms(self):
        scenario = ExperimentScenario(
            scenario_id="m8_terms",
            name="terms",
            project_description="Security review of the authentication module",
            tasks=[
                ExperimentTask(
                    key="a",
                    role="security",
                    description="Resolve credential and permission mistakes.",
                ),
            ],
        )
        assert scenario.tasks[0].role.value == "security"

    def test_secret_looking_values_rejected(self):
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_secret",
                name="secret",
                project_description="use key sk-abc123 in production",
                tasks=[ExperimentTask(key="a", role="backend", description="one")],
            )
        with pytest.raises(Exception):
            ExperimentScenario(
                scenario_id="m8_secret2",
                name="secret2",
                project_description="deploy the platform",
                tasks=[
                    ExperimentTask(
                        key="a",
                        role="backend",
                        description="Set api_key= to the target system.",
                    ),
                ],
            )

    def test_resolve_tasks_is_deterministic_and_resolves_dependencies(self):
        first = low_workload().resolve_tasks(base_timestamp="2026-01-01T00:00:00+00:00")
        second = low_workload().resolve_tasks(base_timestamp="2026-01-01T00:00:00+00:00")
        assert first == second
        assert [t["id"] for t in first] == [
            "TASK-1", "TASK-2", "TASK-3", "TASK-4", "TASK-5",
        ]
        roles = [t["role"] for t in first]
        assert roles == ["architect", "backend", "frontend", "qa", "security"]

    def test_resolve_tasks_uses_declared_statuses_and_retries(self):
        scenario = security_risk()
        tasks = scenario.resolve_tasks(base_timestamp="2026-01-01T00:00:00+00:00")
        statuses = [t["status"] for t in tasks]
        assert statuses.count("FAILED") == 5
        assert statuses.count("RETRY") == 8


# ---- Built-in fixtures -------------------------------------------------------


class TestFixtures:
    def test_all_scenarios_count_and_ids(self):
        scenarios = all_scenarios()
        assert len(scenarios) == 5
        ids = [s.scenario_id for s in scenarios]
        assert len(ids) == len(set(ids))
        for scenario in scenarios:
            assert scenario.name
            assert scenario.description
            assert scenario.project_description.strip()

    def test_fixtures_have_no_terminal_tasks(self):
        for scenario in all_scenarios():
            for task in scenario.tasks:
                assert task.initial_status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

    def test_low_workload_claim(self):
        scenario = low_workload()
        assert len(scenario.tasks) == 5
        assert {t.role.value for t in scenario.tasks} == {
            "architect", "backend", "frontend", "qa", "security",
        }
        assert all(t.initial_status is None for t in scenario.tasks)
        assert scenario.expected_characteristics["adaptive_workload_level"] == "NORMAL"
        assert scenario.expected_characteristics["adaptive_spawn_role"] is None

    def test_high_backend_workload_claim(self):
        scenario = high_backend_workload()
        backend = [t for t in scenario.tasks if t.role.value == "backend"]
        assert scenario.expected_characteristics["backend_tasks"] == 7
        assert len(backend) == 7
        assert sum(1 for t in backend if t.initial_status == TaskStatus.RETRY) == 2
        assert scenario.expected_characteristics["adaptive_workload_level"] == "HIGH"
        assert scenario.expected_characteristics["adaptive_spawn_role"] == "backend"

    def test_high_frontend_workload_mirrors_backend(self):
        scenario = high_frontend_workload()
        frontend = [t for t in scenario.tasks if t.role.value == "frontend"]
        assert scenario.expected_characteristics["frontend_tasks"] == 7
        assert len(frontend) == 7
        assert sum(1 for t in frontend if t.initial_status == TaskStatus.RETRY) == 2
        backend_counts = high_backend_workload().expected_characteristics
        assert scenario.expected_characteristics["adaptive_spawn_role"] == "frontend"
        assert scenario.expected_characteristics["adaptive_workload_level"] == backend_counts["adaptive_workload_level"]

    def test_security_risk_claim(self):
        scenario = security_risk()
        assert scenario.expected_characteristics["task_count"] == 22
        assert len(scenario.tasks) == 22
        security = [t for t in scenario.tasks if t.role.value == "security"]
        assert len(security) == 8
        assert all(t.initial_status == TaskStatus.RETRY for t in security)
        descriptions = " ".join(t.description.lower() for t in scenario.tasks)
        assert "vulnerabilities" in descriptions
        assert scenario.expected_characteristics["adaptive_risk_level"] == "HIGH"

    def test_mixed_high_workload_claim(self):
        scenario = mixed_high_workload()
        assert scenario.expected_characteristics["task_count"] == 13
        assert scenario.expected_characteristics["adaptive_workload_level"] == "ELEVATED"
        assert scenario.expected_characteristics["adaptive_spawn_role"] is None


# ---- Runner ------------------------------------------------------------------


class TestRunScenario:
    def test_fixed_run_produces_complete_record(self):
        record = run_scenario(low_workload(), "fixed", 1)[0]
        data = record.to_dict()
        assert data["strategy"] == "fixed"
        assert data["project_description"] == low_workload().project_description
        assert data["scenario_id"] == "m8_low_workload"
        assert data["run_id"] == "m8_low_workload-fixed-1"
        assert data["metrics"]["task"]["completed_tasks"] == 5
        assert data["metrics"]["adaptive"]["adaptive_decision_count"] == 0
        assert "event_count" in data["metrics"]["timing"]
        assert len(data["raw_events"]) == data["metrics"]["timing"]["event_count"]

    def test_adaptive_run_produces_complete_record(self):
        record = run_scenario(low_workload(), "adaptive", 1)[0]
        data = record.to_dict()
        assert data["strategy"] == "adaptive"
        assert data["run_id"] == "m8_low_workload-adaptive-1"
        assert data["metrics"]["task"]["completed_tasks"] == 5
        assert data["metrics"]["adaptive"]["adaptive_decision_count"] == 1

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValueError):
            run_scenario(low_workload(), "hybrid", 1)

    def test_invalid_repetitions_rejected(self):
        with pytest.raises(ValueError):
            run_scenario(low_workload(), "fixed", 0)
        with pytest.raises(ValueError):
            run_scenario(low_workload(), "fixed", repetitions=-1)
        with pytest.raises(ValueError):
            run_scenario(low_workload(), "fixed", repetitions="many")

    def test_repetitions_produce_distinct_run_ids(self):
        records = run_scenario(low_workload(), "fixed", 3)
        assert len(records) == 3
        ids = [r.to_dict()["run_id"] for r in records]
        assert ids == ["m8_low_workload-fixed-1", "m8_low_workload-fixed-2", "m8_low_workload-fixed-3"]

    def test_custom_run_ids_accepted(self):
        records = run_scenario(
            low_workload(), "fixed", 2, run_ids=["low-a", "low-b"]
        )
        assert [r.to_dict()["run_id"] for r in records] == ["low-a", "low-b"]

    def test_custom_run_ids_must_match_repitions(self):
        with pytest.raises(ValueError):
            run_scenario(low_workload(), "fixed", 2, run_ids=["only-one"])

    def test_records_contain_no_secrets(self):
        import re

        secret_pattern = re.compile(r"(sk-[A-Za-z0-9]{15,}|-----BEGIN|api_key\s*=|password\s*=)")
        for strategy in ("fixed", "adaptive"):
            record = run_scenario(security_risk(), strategy, 1)[0]
            data = json.dumps(record.to_dict())
            assert secret_pattern.search(data) is None
            assert "gemini_api_key" not in data

    def test_both_strategies_share_same_task_set(self):
        scenario = high_backend_workload()
        fixed = run_scenario(scenario, "fixed", 1)[0]
        adaptive = run_scenario(scenario, "adaptive", 1)[0]
        fixed_tasks = _task_signature(fixed.raw_events)
        adaptive_tasks = _task_signature(adaptive.raw_events)
        assert fixed_tasks == adaptive_tasks
        assert len(fixed_tasks) == len(scenario.tasks)

    def test_adaptive_computes_workload_and_risk_series(self):
        record = run_scenario(high_backend_workload(), "adaptive", 1)[0]
        metrics = record.to_dict()["metrics"]
        assert metrics["adaptive"]["workload_score_over_time"]
        assert metrics["adaptive"]["risk_score_over_time"]


class TestStrategyBehaviour:
    def test_fixed_never_spawns_for_any_scenario(self):
        for scenario in [low_workload(), high_backend_workload(), security_risk()]:
            record = run_scenario(scenario, "fixed", 1)[0]
            metrics = record.to_dict()["metrics"]
            assert metrics["agent"]["dynamically_spawned_agents"] == 0

    def test_low_workload_adaptive_continues_only(self):
        record = run_scenario(low_workload(), "adaptive", 1)[0]
        decisions = record.to_dict()["metrics"]["adaptive"]["decisions_by_type"]
        assert decisions == {"CONTINUE": 1}

    def test_high_backend_adaptive_spawns_backend(self):
        record = run_scenario(high_backend_workload(), "adaptive", 1)[0]
        metrics = record.to_dict()["metrics"]
        assert metrics["adaptive"]["spawn_events"] >= 1
        spawned = {
            e.get("agent_id")
            for e in record.raw_events
            if e.get("type") == "agent_spawned"
        }
        assert any(agent_id and agent_id.lower().startswith("backend") for agent_id in spawned)
        assert metrics["adaptive"]["workload_score_over_time"][0]["workload_score"] > 70

    def test_high_frontend_adaptive_spawns_frontend(self):
        record = run_scenario(high_frontend_workload(), "adaptive", 1)[0]
        metrics = record.to_dict()["metrics"]
        assert metrics["adaptive"]["spawn_events"] >= 1
        spawned = {
            e.get("agent_id")
            for e in record.raw_events
            if e.get("type") == "agent_spawned"
        }
        assert any(agent_id and agent_id.lower().startswith("frontend") for agent_id in spawned)
        assert metrics["task"]["completed_tasks"] == 11

    def test_security_risk_adaptive_high_risk_and_spawn(self):
        record = run_scenario(security_risk(), "adaptive", 1)[0]
        metrics = record.to_dict()["metrics"]
        assert metrics["adaptive"]["spawn_events"] >= 1
        spawned = {
            e.get("agent_id")
            for e in record.raw_events
            if e.get("type") == "agent_spawned"
        }
        assert any(agent_id and agent_id.lower().startswith("security") for agent_id in spawned)
        assert metrics["adaptive"]["risk_score_over_time"][0]["risk_score"] > 70
        assert metrics["adaptive"]["workload_score_over_time"][0]["workload_score"] > 70

    def test_mixed_high_workload_no_spawn_and_completes(self):
        # Neither strategy spawns in this scenario; the static fixed baseline
        # drains each role's full backlog and both complete the task set.
        fixed = run_scenario(mixed_high_workload(), "fixed", 1)[0]
        adaptive = run_scenario(mixed_high_workload(), "adaptive", 1)[0]
        assert fixed.to_dict()["metrics"]["adaptive"]["spawn_events"] == 0
        assert adaptive.to_dict()["metrics"]["adaptive"]["spawn_events"] == 0
        assert fixed.to_dict()["metrics"]["task"]["completed_tasks"] == 13
        assert adaptive.to_dict()["metrics"]["task"]["completed_tasks"] == 13
        assert [e.get("type") for e in adaptive.raw_events].count("workflow_completed") == 1

    def test_fixed_completes_expected_backlog_for_each_scenario(self):
        for scenario in all_scenarios():
            expected = scenario.expected_characteristics["fixed_completed_tasks"]
            record = run_scenario(scenario, "fixed", 1)[0]
            completed = record.to_dict()["metrics"]["task"]["completed_tasks"]
            assert completed == expected, scenario.scenario_id

    def test_fixed_static_agent_drains_all_its_tasks_sequentially(self):
        # BACKEND-1 alone executes every one of the seven backend tasks in the
        # high-backend scenario within its single node visit.
        record = run_scenario(high_backend_workload(), "fixed", 1)[0]
        backend_completed = [
            e
            for e in record.raw_events
            if e.get("type") == "task_completed" and e.get("role") == "backend"
        ]
        assert len(backend_completed) == 7
        assert all(e["agent_id"] == "BACKEND-1" for e in backend_completed)

    def test_fixed_fully_drains_backlog_when_dependencies_permit(self):
        # The static organization completes the whole supplied workload for
        # every scenario whose tasks are all startable (no stuck FAILED ones).
        for scenario in [
            low_workload(),
            high_backend_workload(),
            high_frontend_workload(),
            mixed_high_workload(),
        ]:
            record = run_scenario(scenario, "fixed", 1)[0]
            completed = record.to_dict()["metrics"]["task"]["completed_tasks"]
            assert completed == len(scenario.tasks), scenario.scenario_id

    def test_fixed_emits_no_adaptive_actions(self):
        record = run_scenario(security_risk(), "fixed", 1)[0]
        event_types = {e.get("type") for e in record.raw_events}
        assert event_types.isdisjoint(set(ADAPTIVE_ONLY_TYPES))
        metrics = record.to_dict()["metrics"]
        assert metrics["adaptive"]["adaptive_decision_count"] == 0
        assert metrics["adaptive"]["spawn_events"] == 0
        assert metrics["adaptive"]["termination_events"] == 0

    def test_fixed_pool_stays_six_agents_in_all_scenarios(self):
        for scenario in all_scenarios():
            record = run_scenario(scenario, "fixed", 1)[0]
            data = record.to_dict()
            agents = data["metrics"]["agent"]["agents"]
            assert len(agents) == 6, scenario.scenario_id
            assert {a["layout"] for a in agents} == {"baseline"}
            assert data["metrics"]["agent"]["dynamically_spawned_agents"] == 0


class TestEventSchemaParity:
    def test_fixed_and_adaptive_event_schema_parity(self):
        # Scenarios that both strategies fully complete share the same core
        # event schema; only documented adaptive-only types differ.
        for scenario in [
            low_workload(),
            high_backend_workload(),
            high_frontend_workload(),
            mixed_high_workload(),
        ]:
            fixed_types = {
                e.get("type") for e in run_scenario(scenario, "fixed", 1)[0].raw_events
            }
            adaptive_types = {
                e.get("type") for e in run_scenario(scenario, "adaptive", 1)[0].raw_events
            }
            adaptive_core = adaptive_types - set(ADAPTIVE_ONLY_TYPES)
            assert adaptive_core == fixed_types

    def test_fixed_and_adaptive_terminal_completion_events_match(self):
        # Both strategies now share one terminal-state rule for WORKFLOW_COMPLETED.
        # security_risk reaches its terminal state after full execution (17
        # COMPLETED + the 5 FAILED backend seeds), so both emit exactly once and
        # their non-adaptive event sets are identical.
        fixed = run_scenario(security_risk(), "fixed", 1)[0].raw_events
        adaptive = run_scenario(security_risk(), "adaptive", 1)[0].raw_events
        fixed_core = {e.get("type") for e in fixed}
        adaptive_core = {e.get("type") for e in adaptive} - set(ADAPTIVE_ONLY_TYPES)
        assert adaptive_core == fixed_core
        assert "workflow_completed" in fixed_core
        assert "workflow_completed" in adaptive_core
        assert sum(1 for e in fixed if e.get("type") == "workflow_completed") == 1
        assert sum(1 for e in adaptive if e.get("type") == "workflow_completed") == 1

    def test_run_comparison_shape_and_repetitions(self):
        result = run_comparison(low_workload(), repetitions=2)
        assert set(result) == {"scenario", "fixed", "adaptive"}
        assert result["scenario"]["scenario_id"] == "m8_low_workload"
        assert len(result["fixed"]) == 2
        assert len(result["adaptive"]) == 2
        assert result["fixed"][0]["strategy"] == "fixed"

    def test_run_all_scenarios_dataset_is_json_serializable(self):
        dataset = run_all_scenarios(repetitions=1)
        encoded = json.dumps(dataset)
        parsed = json.loads(encoded)
        assert parsed["dataset"] == "ekatra_m8_scenario_dataset"
        assert set(parsed["scenarios"]) == {
            scenario.scenario_id for scenario in all_scenarios()
        }
        for scenario_id, bundle in parsed["scenarios"].items():
            assert set(bundle) == {"scenario", "fixed", "adaptive"}
            assert len(bundle["fixed"]) == 1
            assert len(bundle["adaptive"]) == 1
            assert bundle["fixed"][0]["scenario_id"] == scenario_id
            assert bundle["adaptive"][0]["scenario_id"] == scenario_id

    def test_build_initial_state_carries_scenario_tasks(self):
        state = build_initial_state(high_backend_workload())
        assert state["project_description"] == high_backend_workload().project_description
        assert len(state["tasks"]) == 11
        assert all(t["status"] == "PENDING" or t["status"] in {"RETRY", "FAILED"} for t in state["tasks"])


# ---- Pre-M9 fixes: completion semantics & cycle boundary ---------------------


@pytest.fixture
def adaptive_rounds(monkeypatch):
    """Override max_adaptive_rounds for the duration of a single test."""
    def _apply(n: int) -> None:
        monkeypatch.setattr(
            settings_module,
            "get_settings",
            lambda: Settings(max_adaptive_rounds=n),
        )
    return _apply


def _adaptive_cycles(events: list[dict]) -> list[int]:
    """Explicit execute/adapt cycle count read from adaptation decisions.

    Every loop iteration emits exactly one ADAPTATION_DECISION for its cycle,
    so the sorted cycle numbers are the exact cycle sequence the run executed.
    """
    return sorted(
        e.get("cycle")
        for e in events
        if e.get("type") == "adaptation_decision"
    )


class TestWorkflowCompletedSemantics:
    """Issue 1: fixed and adaptive share one terminal-state completion rule."""

    def test_all_completed_emits_exactly_once_for_both_strategies(self):
        for scenario in all_scenarios():
            for strategy in ("fixed", "adaptive"):
                events = run_scenario(scenario, strategy, 1)[0].raw_events
                finished = [
                    e for e in events if e.get("type") == "workflow_completed"
                ]
                assert len(finished) == 1, (scenario.scenario_id, strategy)

    def test_terminal_failed_with_no_executable_work_emits(self):
        # security_risk ends with every task terminal (17 COMPLETED + 5 FAILED
        # seeds); no task can still run, so both strategies must emit.
        for strategy in ("fixed", "adaptive"):
            events = run_scenario(security_risk(), strategy, 1)[0].raw_events
            assert "workflow_completed" in {e.get("type") for e in events}

    def test_executable_pending_remaining_forbids_premature_emission(
        self, adaptive_rounds
    ):
        # Capping the round limit leaves several security reviews PENDING/RETRY
        # with executable work. The graph still reaches its end, but the shared
        # rule forbids WORKFLOW_COMPLETED while any task can still run.
        adaptive_rounds(2)
        state = run_adaptive(initial_state=build_initial_state(security_risk()))
        assert not workflow_reached_terminal_state(state["tasks"])
        executable = [
            t for t in state["tasks"]
            if t.get("status") in {"PENDING", "ASSIGNED", "RETRY"}
        ]
        assert executable
        assert "workflow_completed" not in {
            e.get("type") for e in state["observability_events"]
        }

    def test_shared_rule_drives_fixed_finalizer_too(self):
        terminal = [
            {"status": "COMPLETED"}, {"status": "FAILED"}, {"status": "CANCELLED"},
        ]
        assert workflow_reached_terminal_state(terminal) is True
        for status in ("PENDING", "ASSIGNED", "RETRY", "RUNNING"):
            incomplete = [{"status": "COMPLETED"}, {"status": status}]
            assert workflow_reached_terminal_state(incomplete) is False
        assert workflow_reached_terminal_state([]) is True

        # The fixed-side decorator path honors the same rule: a final node
        # reaching the end of the graph is not enough while work remains.
        result = {
            "tasks": [{"status": "COMPLETED"}, {"status": "PENDING"}],
            "observability_events": [],
        }
        finalized = finalize_workflow_events(dict(result), "security")
        assert "workflow_completed" not in {
            e.get("type") for e in finalized["observability_events"]
        }
        result["tasks"][1]["status"] = "FAILED"
        finalized = finalize_workflow_events(result, "security")
        assert "workflow_completed" in {
            e.get("type") for e in finalized["observability_events"]
        }


class TestAdaptiveMaxRoundsBoundary:
    """Issue 2: max_adaptive_rounds = N allows at most N execute/adapt cycles."""

    def test_max_one_allows_exactly_one_cycle(self, adaptive_rounds):
        adaptive_rounds(1)
        events = run_scenario(security_risk(), "adaptive", 1)[0].raw_events
        assert _adaptive_cycles(events) == [1]

    def test_max_two_allows_exactly_two_cycles(self, adaptive_rounds):
        adaptive_rounds(2)
        events = run_scenario(security_risk(), "adaptive", 1)[0].raw_events
        assert _adaptive_cycles(events) == [1, 2]

    def test_termination_at_configured_max(self, adaptive_rounds):
        adaptive_rounds(3)
        events = run_scenario(security_risk(), "adaptive", 1)[0].raw_events
        assert _adaptive_cycles(events) == [1, 2, 3]

    def test_max_eight_runs_eight_not_seven_with_no_hidden_extra(
        self, adaptive_rounds
    ):
        # Regression: the old guard (cycle >= max_rounds) ended after only
        # seven execute/adapt rounds when max_adaptive_rounds == 8.
        adaptive_rounds(8)
        state = run_adaptive(initial_state=build_initial_state(security_risk()))
        assert _adaptive_cycles(state["observability_events"]) == list(range(1, 9))
        assert len(state["adaptive_decisions"]) == 8
        assert state["adaptive_cycle"] == 9  # one past the final executed round
        assert workflow_reached_terminal_state(state["tasks"])

    def test_early_completion_stops_before_max(self, adaptive_rounds):
        adaptive_rounds(8)
        state = run_adaptive(initial_state=build_initial_state(low_workload()))
        assert _adaptive_cycles(state["observability_events"]) == [1]
        assert state["adaptive_cycle"] == 2

    def test_no_infinite_loop_when_work_cannot_finish(self, adaptive_rounds):
        adaptive_rounds(2)
        state = run_adaptive(initial_state=build_initial_state(security_risk()))
        decision_events = [
            e for e in state["observability_events"]
            if e.get("type") == "adaptation_decision"
        ]
        assert len(decision_events) == 2
        assert state["adaptive_cycle"] == 3


# ---- helpers -----------------------------------------------------------------


def _task_signature(events: list[dict]) -> list[tuple[str, str, int]]:
    """Return (task_id, role, priority) from the task_created events."""
    created = [e for e in events if e.get("type") == "task_created"]
    return sorted((e["task_id"], e["role"], e["priority"]) for e in created)