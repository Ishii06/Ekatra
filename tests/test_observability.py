"""Milestone 7 test suite: observability & metrics.

Covers the required >=20 scenarios using fully injected, deterministic
timestamps (no wall-clock dependence):

workflow timing, task durations, waiting time, queue length, active-agent
tracking (series / peak / average), utilization incl. spawned-agent lifetimes,
spawn/termination recording, reassignment, adaptive decisions, communication,
tools, quality observations, experiment record (JSON + CSV), secret exclusion,
fixed metrics, adaptive metrics, fixed/adaptive schema parity, and end-to-end
emission of events by all three workflows. The existing 180-test suite must
stay green alongside.
"""

from __future__ import annotations

import json

import pytest

from ekatra.config.settings import get_settings
from ekatra.observability.clock import Clock, parse_ts, seconds_between
from ekatra.observability.events import EventLog, EventType, make_event
from ekatra.observability.experiment import ExperimentRecord, new_run_id
from ekatra.observability.integration import (
    ADAPTIVE_ONLY_TYPES,
    agent_spawned_event,
    agent_terminated_event,
    decision_events,
)
from ekatra.observability.metrics import (
    compute_metrics,
    compute_quality_metrics,
)

T0 = "2026-01-01T10:00:00+00:00"
T1 = "2026-01-01T10:01:00+00:00"
T2 = "2026-01-01T10:05:00+00:00"


def task(task_id: str, role: str, started: str, completed: str, agent: str) -> dict:
    """A completed task dict with deterministic UTC timestamps."""
    return {
        "id": task_id,
        "description": f"task {task_id}",
        "role": role,
        "priority": 1,
        "complexity": 2,
        "dependencies": [],
        "risk": 10,
        "status": "COMPLETED",
        "assigned_agent": agent,
        "retry_count": 0,
        "output": "ok",
        "created_at": T0,
        "assigned_at": T0,
        "started_at": started,
        "completed_at": completed,
        "priority_history": [],
    }


def agents() -> list[dict]:
    return [
        {"agent_id": "PM-1", "role": "project_manager", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
        {"agent_id": "ARCH-1", "role": "architect", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
        {"agent_id": "BACK-1", "role": "backend", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
        {"agent_id": "FRONT-1", "role": "frontend", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
        {"agent_id": "QA-1", "role": "qa", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
        {"agent_id": "SEC-1", "role": "security", "status": "ACTIVE",
         "current_task": None, "metadata": {}, "strategy": "mock"},
    ]


def fixed_tasks() -> list[dict]:
    return [
        task("TASK-1", "architect", "2026-01-01T10:01:00+00:00",
             "2026-01-01T10:05:00+00:00", "ARCH-1"),
        task("TASK-2", "backend", "2026-01-01T10:06:00+00:00",
             "2026-01-01T10:11:00+00:00", "BACK-1"),
        task("TASK-3", "frontend", "2026-01-01T10:12:00+00:00",
             "2026-01-01T10:16:00+00:00", "FRONT-1"),
        task("TASK-4", "qa", "2026-01-01T10:17:00+00:00",
             "2026-01-01T10:20:00+00:00", "QA-1"),
        task("TASK-5", "security", "2026-01-01T10:21:00+00:00",
             "2026-01-01T10:25:00+00:00", "SEC-1"),
    ]


def workflow_events() -> list[dict]:
    started = make_event(EventType.WORKFLOW_STARTED, T0,
                         project_description="demo").to_dict()
    completed = make_event(EventType.WORKFLOW_COMPLETED,
                           "2026-01-01T10:25:00+00:00",
                           final_step="security").to_dict()
    return [started, completed]


def fixed_state() -> dict:
    """A complete fixed-style final state with all required observability data."""
    return {
        "project_description": "demo",
        "tasks": fixed_tasks(),
        "agents": agents(),
        "communication": fixed_messages(),
        "tool_calls": tool_calls(),
        "adaptive_decisions": [],
        "observability_events": workflow_events(),
    }


def decision_dict(decision: str, cycle: int, timestamp: str, **overrides) -> dict:
    base = {
        "timestamp": timestamp,
        "cycle": cycle,
        "decision": decision,
        "workload_score": 0.0,
        "risk_score": 0.0,
        "workload_level": "NORMAL",
        "risk_level": "NORMAL",
        "reason": "deterministic",
        "affected_role": None,
        "affected_agent": None,
        "affected_task": None,
        "previous_state": {},
        "resulting_state": {},
    }
    base.update(overrides)
    return base


def fixed_messages() -> list[dict]:
    return [
        {"message_id": "m1", "sender_agent": "PM-1", "recipient_agent": "*",
         "message_type": "STATUS_UPDATE", "content": "plan",
         "related_task_id": None, "timestamp": T0},
        {"message_id": "m2", "sender_agent": "PM-1", "recipient_agent": "ARCH-1",
         "message_type": "TASK_ASSIGNMENT", "content": "a",
         "related_task_id": "TASK-1", "timestamp": T0},
        {"message_id": "m3", "sender_agent": "ARCH-1", "recipient_agent": "BACK-1",
         "message_type": "RESULT", "content": "r",
         "related_task_id": "TASK-1", "timestamp": T2},
        {"message_id": "m4", "sender_agent": "ARCH-1", "recipient_agent": "FRONT-1",
         "message_type": "RESULT", "content": "r",
         "related_task_id": "TASK-1", "timestamp": T2},
        {"message_id": "m5", "sender_agent": "BACK-1", "recipient_agent": "QA-1",
         "message_type": "RESULT", "content": "r",
         "related_task_id": "TASK-2", "timestamp": T1},
        {"message_id": "m6", "sender_agent": "SEC-1", "recipient_agent": "PM-1",
         "message_type": "RESULT", "content": "done",
         "related_task_id": "TASK-5", "timestamp": T2},
    ]


def tool_calls() -> list[dict]:
    return [
        {"tool_name": "inspect_path", "agent_id": "PM-1", "success": True,
         "duration_ms": 12.5, "task_id": "PLAN",
         "timestamp": "2026-01-01T10:00:01+00:00"},
        {"tool_name": "write_file", "agent_id": "BACK-1", "success": False,
         "duration_ms": 200.0, "task_id": "TASK-2",
         "timestamp": "2026-01-01T10:06:05+00:00"},
        {"tool_name": "write_file", "agent_id": "BACK-1", "success": True,
         "duration_ms": 80.0, "task_id": "TASK-2",
         "timestamp": "2026-01-01T10:06:08+00:00"},
    ]


def adaptive_state() -> dict:
    """An adaptive-style final state with spawn + terminate + decisions."""
    spawned = fixed_state()
    spawned["agents"] = agents() + [
        {"agent_id": "BACK-2", "role": "backend", "status": "COMPLETED",
         "current_task": None, "metadata": {}, "strategy": "mock"},
    ]
    spawned["tasks"] = fixed_tasks() + [
        task("TASK-6", "backend", "2026-01-01T10:10:00+00:00",
             "2026-01-01T10:13:00+00:00", "BACK-2"),
    ]
    decisions = [
        decision_dict(
            "CONTINUE", 1, "2026-01-01T10:00:30+00:00",
            workload_score=20.0, risk_score=10.0,
            workload_level="LOW", risk_level="LOW",
            reason="no change", resulting_state={"action": "none"},
        ),
        decision_dict(
            "SPAWN", 2, "2026-01-01T10:00:40+00:00",
            workload_score=82.0, risk_score=55.0,
            workload_level="HIGH", risk_level="MONITOR",
            reason="queue overload", affected_role="backend",
            resulting_state={"spawned_agent": "BACK-2", "role": "backend"},
        ),
    ]
    spawned["adaptive_decisions"] = decisions
    spawned["observability_events"] = workflow_events() + [
        agent_spawned_event("BACK-2", "backend", "2026-01-01T10:00:40+00:00"),
        agent_terminated_event("BACK-2", "backend", "2026-01-01T10:20:00+00:00"),
    ]
    return spawned


# -- timing / clock -----------------------------------------------------------


def test_clock_is_injectable_and_deterministic():
    clock = Clock(now=lambda: "2026-01-01T00:00:00+00:00")
    assert clock.now() == "2026-01-01T00:00:00+00:00"
    assert seconds_between("2026-01-01T00:00:00+00:00",
                           "2026-01-01T00:02:00+00:00") == 120.0
    assert seconds_between(None, "2026-01-01T00:02:00+00:00") == 0.0
    assert seconds_between("2026-01-01T00:02:00+00:00",
                           "2026-01-01T00:01:00+00:00") == 0.0
    assert parse_ts("") is None


def test_workflow_timing_record():
    bundle = compute_metrics(fixed_state())
    timing = bundle.timing
    assert timing["workflow_started_at"] == T0
    assert timing["workflow_completed_at"] == "2026-01-01T10:25:00+00:00"
    assert timing["duration_seconds"] == 1500.0
    assert timing["event_count"] == 2


# -- task metrics -------------------------------------------------------------


def test_task_completion_duration_calculation():
    bundle = compute_metrics(fixed_state())
    durations = {d["task_id"]: d["duration_seconds"]
                 for d in bundle.task["task_completion_durations"]}
    assert durations == {
        "TASK-1": 240.0, "TASK-2": 300.0, "TASK-3": 240.0,
        "TASK-4": 180.0, "TASK-5": 240.0,
    }
    assert bundle.task["total_task_completion_time_seconds"] == 1200.0
    assert bundle.task["average_task_completion_time_seconds"] == 240.0
    assert bundle.task["completed_tasks"] == 5
    assert bundle.task["failed_tasks"] == 0


def test_task_waiting_time():
    bundle = compute_metrics(fixed_state())
    waits = {w["task_id"]: w["waiting_seconds"]
             for w in bundle.task["task_waiting_durations"]}
    assert waits == {
        "TASK-1": 60.0, "TASK-2": 360.0, "TASK-3": 720.0,
        "TASK-4": 1020.0, "TASK-5": 1260.0,
    }
    assert bundle.task["total_task_waiting_time_seconds"] == 3420.0
    assert bundle.task["average_task_waiting_time_seconds"] == 684.0


def test_queue_length_over_time():
    bundle = compute_metrics(fixed_state())
    queue = bundle.task["queue_length_over_time"]
    assert queue[0]["queue_length"] == 5
    assert queue[-1]["queue_length"] == 0
    samples = [s["queue_length"] for s in queue]
    assert samples == sorted(samples, reverse=True)


# -- agent metrics ------------------------------------------------------------


def test_active_agents_series():
    bundle = compute_metrics(fixed_state())
    active = bundle.agent["active_agents_over_time"]
    # tasks run strictly sequentially, so concurrency only ever reaches 1
    assert any(s["active_agents"] == 1 for s in active)
    assert all(s["active_agents"] in (0, 1) for s in active)


def test_peak_active_agents():
    bundle = compute_metrics(fixed_state())
    assert bundle.agent["peak_active_agents"] == 1


def test_average_active_agents():
    bundle = compute_metrics(fixed_state())
    # 1200s of active time across a 1500s workflow -> 0.8 average concurrency
    assert abs(bundle.agent["average_active_agents"] - 0.8) < 1e-6


def test_agent_utilization_baseline_window():
    bundle = compute_metrics(fixed_state())
    records = {r["agent_id"]: r for r in bundle.agent["agents"]}
    assert records["ARCH-1"]["available_seconds"] == 1500.0
    assert records["ARCH-1"]["active_seconds"] == 240.0
    assert records["ARCH-1"]["layout"] == "baseline"
    assert records["ARCH-1"]["execution_count"] == 1
    # aggregate = total active (1200s) / total available (6 * 1500s)
    assert abs(bundle.agent["agent_utilization"] - 1200.0 / 9000.0) < 1e-6


def test_utilization_spawned_agent_lifetime_window():
    state = adaptive_state()
    bundle = compute_metrics(state)
    records = {r["agent_id"]: r for r in bundle.agent["agents"]}
    back2 = records["BACK-2"]
    assert back2["layout"] == "dynamic"
    # available window = [spawn 10:00:40, min(terminate 10:20:00, end 10:25:00)]
    assert back2["available_seconds"] == pytest.approx(19 * 60 + 20)
    assert back2["active_seconds"] == 180.0  # 10:10 -> 10:13
    baseline = records["BACK-1"]
    assert baseline["layout"] == "baseline"
    assert baseline["available_seconds"] == 1500.0


def test_spawn_and_termination_recording():
    bundle = compute_metrics(adaptive_state())
    assert bundle.agent["dynamically_spawned_agents"] == 1
    assert bundle.agent["dynamically_terminated_agents"] == 1
    assert bundle.adaptive["spawn_events"] == 1
    assert bundle.adaptive["termination_events"] == 1


# -- adaptive metrics ---------------------------------------------------------


def test_adaptive_decision_metrics():
    bundle = compute_metrics(adaptive_state())
    assert bundle.adaptive["adaptive_decision_count"] == 2
    assert bundle.adaptive["decisions_by_type"] == {"CONTINUE": 1, "SPAWN": 1}
    series = bundle.adaptive["workload_score_over_time"]
    assert series[0]["workload_score"] == 20.0
    assert series[1]["workload_score"] == 82.0
    risk = bundle.adaptive["risk_score_over_time"]
    assert risk[1]["risk_score"] == 55.0


def test_reassignment_and_prioritization_events_from_decisions():
    reassign = decision_dict(
        "REASSIGN", 3, "2026-01-01T10:01:00+00:00",
        affected_task="TASK-2", affected_agent="BACK-2",
        reason="slow backlog",
        previous_state={"assigned_agent": "BACK-1"},
        resulting_state={"reassigned_task": "TASK-2", "to_agent": "BACK-2"},
    )
    prioritize = decision_dict(
        "PRIORITIZE", 4, "2026-01-01T10:02:00+00:00",
        affected_task="TASK-3", reason="blocker",
        previous_state={"priority": 2},
        resulting_state={"prioritized_task": "TASK-3", "priority": 1},
    )
    events = decision_events(reassign) + decision_events(prioritize)
    types = {e["type"] for e in events}
    assert "task_reassigned" in types
    assert "task_prioritized" in types
    assert types <= ADAPTIVE_ONLY_TYPES
    reassigned = [e for e in events if e["type"] == "task_reassigned"]
    assert reassigned[0]["to_agent"] == "BACK-2"
    assert reassigned[0]["from_agent"] == "BACK-1"
    prioritized = [e for e in events if e["type"] == "task_prioritized"]
    assert prioritized[0]["new_priority"] == 1


def test_spawn_decision_produces_agent_spawned_event():
    spawn = decision_dict(
        "SPAWN", 2, "2026-01-01T10:00:40+00:00",
        affected_role="backend",
        resulting_state={"spawned_agent": "BACK-2", "role": "backend"},
    )
    events = decision_events(spawn)
    spawned = [e for e in events if e["type"] == "agent_spawned"]
    assert len(spawned) == 1
    assert spawned[0]["agent_id"] == "BACK-2"
    decision = [e for e in events if e["type"] == "adaptation_decision"]
    assert len(decision) == 1


# -- communication / tools / quality ------------------------------------------


def test_communication_metrics():
    bundle = compute_metrics(fixed_state())
    comm = bundle.communication
    assert comm["total_messages"] == 6
    assert comm["messages_by_type"]["RESULT"] == 4
    assert comm["messages_by_sender"]["ARCH-1"] == 2
    assert comm["messages_by_recipient"]["PM-1"] == 1
    assert comm["messages_by_recipient"]["*"] == 1
    assert comm["task_related_messages"] == 5


def test_tool_metrics():
    bundle = compute_metrics(fixed_state())
    tools = bundle.tools
    assert tools["total_tool_calls"] == 3
    assert tools["calls_by_tool"] == {"inspect_path": 1, "write_file": 2}
    assert tools["calls_by_agent"] == {"PM-1": 1, "BACK-1": 2}
    assert tools["successful_calls"] == 2
    assert tools["failed_calls"] == 1
    assert tools["total_tool_duration_ms"] == pytest.approx(292.5)
    assert tools["average_tool_duration_ms"] == pytest.approx(97.5)


def test_quality_observation_recording():
    events = workflow_events() + [
        {"type": "quality_observation", "timestamp": "2026-01-01T10:25:01+00:00",
         "category": "test_results", "result": "pass", "details": "12 tests"},
        {"type": "quality_observation", "timestamp": "2026-01-01T10:25:02+00:00",
         "category": "security_findings", "result": "none",
         "details": "no findings"},
    ]
    quality = compute_quality_metrics(events)
    assert quality["quality_observation_count"] == 2
    assert quality["counts_by_category"] == {
        "test_results": 1, "security_findings": 1,
    }
    assert quality["counts_by_result"] == {"pass": 1, "none": 1}
    state = fixed_state()
    state["observability_events"] = events
    record = ExperimentRecord.from_metrics(
        "fixed", "demo", compute_metrics(state), events
    )
    assert len(record.quality_observations) == 2


def test_quality_metrics_never_invent_scores():
    # With no observations nothing is fabricated: count is 0, no score keys.
    quality = compute_quality_metrics(workflow_events())
    assert quality["quality_observation_count"] == 0
    assert "quality_score" not in quality


# -- event model --------------------------------------------------------------


def test_event_model_is_json_safe_and_flat():
    event = make_event(EventType.TASK_STARTED, T1,
                       task_id="TASK-1", agent_id="ARCH-1")
    d = event.to_dict()
    assert d == {"type": "task_started", "timestamp": T1,
                 "task_id": "TASK-1", "agent_id": "ARCH-1"}
    assert isinstance(json.dumps(d), str)
    assert d["type"] == EventType.TASK_STARTED.value


def test_event_log_is_append_only_and_filterable():
    log = EventLog()
    log.add(make_event(EventType.WORKFLOW_STARTED, T0))
    log.add(make_event(EventType.TASK_CREATED, T0))
    log.add(make_event(EventType.TASK_CREATED, T0))
    assert len(log) == 3
    assert len(log.of_type(EventType.TASK_CREATED)) == 2
    assert log.to_dicts()[0]["type"] == "workflow_started"
    log.add(make_event(EventType.TASK_CREATED, T0))
    assert len(log.of_type(EventType.TASK_CREATED)) == 3


def test_event_type_set_is_exactly_the_required_types():
    expected = {
        "workflow_started", "workflow_completed",
        "task_created", "task_assigned", "task_started", "task_completed",
        "task_failed", "task_retried",
        "agent_spawned", "agent_terminated",
        "task_reassigned", "task_prioritized",
        "adaptation_decision", "tool_executed", "quality_observation",
    }
    assert {t.value for t in EventType} == expected


# -- experiment record --------------------------------------------------------


def test_experiment_record_serialization_round_trip():
    bundle = compute_metrics(fixed_state())
    events = workflow_events()
    record = ExperimentRecord.from_metrics(
        "fixed", "demo", bundle, events, run_id="run-test-1"
    )
    assert record.run_id == "run-test-1"
    assert record.strategy == "fixed"
    assert record.task_summary["completed_tasks"] == 5

    restored = ExperimentRecord.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()

    payload = record.to_json()
    reparsed = ExperimentRecord.from_json(payload)
    assert reparsed.to_dict() == record.to_dict()


def test_experiment_record_csv_export():
    bundle = compute_metrics(fixed_state())
    record = ExperimentRecord.from_metrics("fixed", "demo", bundle, workflow_events())
    tables = record.to_csv()
    assert "events.csv" in tables
    assert "task_durations.csv" in tables
    header = tables["task_durations.csv"].splitlines()[0]
    assert "task_id" in header and "duration_seconds" in header


def test_experiment_record_excludes_secrets(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-EKATRA-SECRET-123")
    bundle = compute_metrics(fixed_state())
    events = workflow_events() + [
        {"type": "task_completed", "timestamp": T2, "task_id": "TASK-1"},
    ]
    clean = ExperimentRecord.from_metrics("fixed", "demo", bundle, events)
    assert not clean.contains_secrets()

    leaked = ExperimentRecord.from_metrics(
        "fixed", "demo", bundle,
        [{"type": "tool_executed", "timestamp": T1,
          "tool_name": "x", "content": "AIza-EKATRA-SECRET-123"}],
    )
    assert leaked.contains_secrets()


def test_new_run_id_is_unique():
    assert new_run_id().startswith("run-")
    assert new_run_id() != new_run_id()


def test_workflow_started_event_has_no_secrets():
    payload = json.dumps(ExperimentRecord().to_dict())
    assert "gemini_api_key" not in payload
    assert "api_key" not in payload


# -- strategy parity ----------------------------------------------------------


def test_fixed_strategy_produces_valid_metrics():
    bundle = compute_metrics(fixed_state())
    assert bundle.task["total_tasks"] == 5
    assert bundle.task["failed_tasks"] == 0
    assert bundle.agent["initial_agent_count"] == 6
    assert bundle.adaptive["adaptive_decision_count"] == 0
    assert bundle.adaptive["spawn_events"] == 0
    assert bundle.adaptive["termination_events"] == 0
    assert bundle.tools["total_tool_calls"] == 3
    assert bundle.communication["total_messages"] == 6
    # no adaptive-only event types exist in a fixed run
    event_types = {e["type"] for e in fixed_state()["observability_events"]}
    assert event_types.isdisjoint(ADAPTIVE_ONLY_TYPES)


def test_adaptive_strategy_produces_valid_metrics():
    bundle = compute_metrics(adaptive_state())
    assert bundle.task["total_tasks"] == 6
    assert bundle.adaptive["adaptive_decision_count"] == 2
    assert bundle.adaptive["spawn_events"] == 1
    assert bundle.adaptive["workload_score_over_time"][-1]["workload_score"] == 82.0
    assert bundle.agent["dynamically_spawned_agents"] == 1


def test_fixed_adaptive_schema_parity():
    fixed = compute_metrics(fixed_state())
    adaptive = compute_metrics(adaptive_state())
    expected = {"timing", "task", "agent", "adaptive", "communication", "tools", "quality"}
    assert set(fixed.to_dict()) == expected
    assert set(adaptive.to_dict()) == expected
    for category in expected:
        assert set(fixed.to_dict()[category]) == set(adaptive.to_dict()[category])


def test_summary_flattens_only_scalars():
    bundle = compute_metrics(fixed_state())
    summary = bundle.to_summary()
    assert summary["task.completed_tasks"] == 5
    assert all(isinstance(v, (int, float, str, bool)) or v is None
               for v in summary.values())


# -- end-to-end workflow instrumentation --------------------------------------


def test_fixed_graph_emits_observability_events():
    from ekatra.graph import run
    from ekatra.state.state import create_initial_state

    result = run(create_initial_state("Build a simple todo application."))
    events = result.get("observability_events", [])
    types = [e["type"] for e in events]
    assert types[0] == "workflow_started"
    assert types[-1] == "workflow_completed"
    assert types.count("task_created") == 5
    assert types.count("task_assigned") == 5
    assert types.count("task_started") == 5
    assert types.count("task_completed") == 5
    assert result["adaptive_decisions"] == []
    bundle = compute_metrics(result)
    assert bundle.timing["duration_seconds"] >= 0
    assert bundle.task["completed_tasks"] == 5
    assert bundle.adaptive["adaptive_decision_count"] == 0


def test_adaptive_graph_emits_observability_events():
    from ekatra.graph.adaptive import run_adaptive

    result = run_adaptive("Build a simple todo application.")
    events = result.get("observability_events", [])
    types = [e["type"] for e in events]
    assert "workflow_started" in types
    assert "workflow_completed" in types
    assert "adaptation_decision" in types
    assert types.count("task_completed") == 5
    decisions = result.get("adaptive_decisions", [])
    bundle = compute_metrics(result)
    assert bundle.adaptive["adaptive_decision_count"] == len(decisions)
    # every SPAWN decision has a matching spawn event
    spawn_events = [e for e in events if e["type"] == "agent_spawned"]
    spawned_in_decisions = sum(
        1 for d in decisions
        if d.get("resulting_state", {}).get("spawned_agent")
    )
    assert len(spawn_events) == spawned_in_decisions
    assert bundle.task["completed_tasks"] == 5


def test_tools_demo_emits_observability_events(tmp_path):
    from ekatra.graph.tools import run_tools_demo

    result = run_tools_demo("Build a simple todo application.", str(tmp_path))
    events = result.get("observability_events", [])
    types = [e["type"] for e in events]
    assert types[-1] == "workflow_completed"
    assert types.count("task_completed") == 5
    tool_events = [e for e in events if e["type"] == "tool_executed"]
    assert len(tool_events) == len(result.get("tool_calls", []))
    bundle = compute_metrics(result)
    assert bundle.tools["total_tool_calls"] == len(result.get("tool_calls", []))


def test_task_model_utc_and_assigned_at():
    from ekatra.agents import Role
    from ekatra.tasks import TaskManager

    manager = TaskManager()
    t = manager.create(role=Role.ARCHITECT, description="x")
    assert t.created_at.tzinfo is not None
    assert t.assigned_at is None
    manager.assign(t.id, "ARCH-1")
    assert t.assigned_at is not None
    assert t.assigned_at.tzinfo is not None
    d = t.to_dict()
    assert d["assigned_at"] is not None
    parsed_created = parse_ts(d["created_at"])
    assert parsed_created is not None and parsed_created.tzinfo is not None

    manager.start(t.id)
    assert t.started_at.tzinfo is not None