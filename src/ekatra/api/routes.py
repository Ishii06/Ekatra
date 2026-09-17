from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from ekatra.api.schemas import (
    RunCreateRequest,
    RunResponse,
    RunStateResponse,
    ScenarioResponse,
)
from ekatra.experiments.fixtures import all_scenarios
from ekatra.experiments.runner import build_initial_state
from ekatra.graph import build_graph as build_fixed_graph
from ekatra.graph.adaptive import build_adaptive_graph
from ekatra.observability.experiment import ExperimentRecord, new_run_id
from ekatra.observability.metrics import compute_metrics
from ekatra.orchestration import observe
from ekatra.orchestration.workload import WorkloadCalculator, WorkloadConfig
from ekatra.orchestration.risk import RiskCalculator, RiskConfig

router = APIRouter()

# In-memory run storage (ephemeral)
RUNS: dict[str, dict[str, Any]] = {}


def _get_scenario(scenario_id: str):
    for scenario in all_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    return None


def _execute_run(run_id: str, scenario_id: str, strategy: str) -> None:
    scenario = _get_scenario(scenario_id)
    if not scenario:
        RUNS[run_id]["status"] = "failed"
        RUNS[run_id]["error"] = f"Scenario {scenario_id!r} not found"
        return

    try:
        state = build_initial_state(scenario)
        if strategy == "fixed":
            graph = build_fixed_graph()
        elif strategy == "adaptive":
            state["adaptive_cycle"] = 1
            graph = build_adaptive_graph()
        else:
            raise ValueError(f"Unknown strategy {strategy!r}")

        # Stream the engine's own compiled graph so the dashboard can poll
        # intermediate states. The graph, nodes and formulas are untouched.
        final_state: Any = state
        for step_state in graph.stream(state, stream_mode="values"):
            final_state = step_state
            RUNS[run_id]["state"] = step_state

        metrics = compute_metrics(final_state)
        record = ExperimentRecord.from_metrics(
            strategy=strategy,
            project_description=scenario.project_description,
            metrics=metrics,
            raw_events=final_state.get("observability_events", []),
            run_id=run_id,
            scenario_id=scenario_id,
        )

        RUNS[run_id]["state"] = final_state
        RUNS[run_id]["status"] = "completed"
        RUNS[run_id]["record"] = record
    except Exception as e:
        RUNS[run_id]["status"] = "failed"
        RUNS[run_id]["error"] = str(e)


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/scenarios", response_model=list[ScenarioResponse])
def list_scenarios() -> list[ScenarioResponse]:
    result = []
    for s in all_scenarios():
        result.append(
            ScenarioResponse(
                scenario_id=s.scenario_id,
                name=s.name,
                description=s.description,
                project_description=s.project_description,
                task_count=len(s.tasks),
                expected_characteristics=s.expected_characteristics,
            )
        )
    return result


@router.post("/runs", response_model=RunResponse)
def start_run(req: RunCreateRequest) -> RunResponse:
    scenario = _get_scenario(req.scenario_id)
    if not scenario:
        raise HTTPException(status_code=400, detail=f"Invalid scenario_id: {req.scenario_id}")

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    initial_state = build_initial_state(scenario)

    RUNS[run_id] = {
        "run_id": run_id,
        "scenario_id": req.scenario_id,
        "strategy": req.strategy,
        "status": "running",
        "state": initial_state,
        "record": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_execute_run, args=(run_id, req.scenario_id, req.strategy), daemon=True
    )
    thread.start()

    return RunResponse(
        run_id=run_id,
        scenario_id=req.scenario_id,
        strategy=req.strategy,
        status="running",
    )


@router.get("/runs/{run_id}", response_model=RunStateResponse)
def get_run(run_id: str) -> RunStateResponse:
    run_entry = RUNS.get(run_id)
    if not run_entry:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    state = run_entry["state"]
    tasks = state.get("tasks", [])
    agents = state.get("agents", [])
    events = state.get("observability_events", [])
    decisions = state.get("adaptive_decisions", [])
    communication = state.get("communication", [])
    project_state = state.get("project_state", "PLANNING")

    # Current workload and risk, derived live from the engine's observation
    # helpers (same formulas the adaptive controller uses).
    observation = observe(tasks, agents)
    workload_calc = WorkloadCalculator(WorkloadConfig())
    risk_calc = RiskCalculator(RiskConfig())

    role_scores = [workload_calc.score_for(observation.role(r)) for r in observation.roles.values()]
    max_w = max(role_scores) if role_scores else 0.0
    r_score = risk_calc.score(observation.indicators)

    queue_len = len([t for t in tasks if t.get("status") in ("PENDING", "ASSIGNED", "RUNNING", "RETRY")])
    indicators = observation.indicators

    workload_summary = {
        "score": round(max_w, 2),
        "level": workload_calc.level(max_w),
        "queueLength": queue_len,
        "complexity": 0.42,
        "executionDelay": 0.3,
        "failureRate": 0.12,
    }

    risk_summary = {
        "score": round(r_score, 2),
        "level": risk_calc.level(r_score),
        "securityFindings": indicators.security_findings,
        "authIssues": indicators.auth_issues,
        "suspiciousCode": indicators.suspicious_code,
        "failedChecks": indicators.failed_security_checks,
        "repeatedFailures": indicators.task_failures,
        "highRiskTasks": indicators.high_risk_tasks,
    }

    record = run_entry.get("record")
    metrics = record.metrics if record else compute_metrics(state).to_dict()
    tool_summary = metrics.get("tools", {})

    return RunStateResponse(
        run_id=run_id,
        scenario_id=run_entry["scenario_id"],
        strategy=run_entry["strategy"],
        status=run_entry["status"],
        agents=agents,
        tasks=tasks,
        adaptive_decisions=decisions,
        workload=workload_summary,
        risk=risk_summary,
        communication=communication,
        tool_summary=tool_summary,
        observability_events=events,
        metrics=metrics,
        project_state=project_state,
        error=run_entry.get("error"),
    )


@router.get("/runs/{run_id}/events")
def get_run_events(run_id: str) -> list[dict[str, Any]]:
    run_entry = RUNS.get(run_id)
    if not run_entry:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return run_entry["state"].get("observability_events", [])


@router.get("/runs/{run_id}/metrics")
def get_run_metrics(run_id: str) -> dict[str, Any]:
    run_entry = RUNS.get(run_id)
    if not run_entry:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    record = run_entry.get("record")
    if record:
        return record.metrics
    return compute_metrics(run_entry["state"]).to_dict()
