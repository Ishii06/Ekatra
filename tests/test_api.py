from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from ekatra.api.app import app
from ekatra.api.routes import RUNS

client = TestClient(app)


def _wait_for_completion(run_id: str, timeout_seconds: float = 10.0) -> dict:
    deadline = time.time() + timeout_seconds
    run_data = None
    while time.time() < deadline:
        run_data = client.get(f"/api/runs/{run_id}").json()
        if run_data["status"] in ("completed", "failed"):
            return run_data
        time.sleep(0.1)
    assert run_data is not None
    return run_data


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_scenarios_endpoint() -> None:
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    scenarios = response.json()
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 5
    ids = [s["scenario_id"] for s in scenarios]
    assert "m8_high_backend_workload" in ids
    assert "m8_low_workload" in ids
    for scenario in scenarios:
        assert scenario["task_count"] >= 1
        assert scenario["name"]


def test_run_lifecycle_adaptive() -> None:
    res = client.post(
        "/api/runs",
        json={"scenario_id": "m8_high_backend_workload", "strategy": "adaptive"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["scenario_id"] == "m8_high_backend_workload"
    assert data["strategy"] == "adaptive"
    assert data["status"] in ("running", "completed")

    run_id = data["run_id"]
    run_data = _wait_for_completion(run_id)

    assert run_data["status"] == "completed"
    assert len(run_data["tasks"]) == 11
    assert "metrics" in run_data
    assert len(run_data["adaptive_decisions"]) >= 1

    spawns = [d for d in run_data["adaptive_decisions"] if d["decision"] == "SPAWN"]
    assert spawns, "adaptive backend scenario should record a SPAWN decision"
    assert spawns[0]["affected_agent"] == "BACKEND-2"
    backend_ids = {a["agent_id"] for a in run_data["agents"] if a["role"] == "backend"}
    assert "BACKEND-2" in backend_ids

    events_res = client.get(f"/api/runs/{run_id}/events")
    assert events_res.status_code == 200
    assert isinstance(events_res.json(), list)

    metrics_res = client.get(f"/api/runs/{run_id}/metrics")
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert metrics["task"]["total_tasks"] == 11
    assert metrics["adaptive"]["spawn_events"] == 1


def test_run_lifecycle_fixed_no_adaptation() -> None:
    res = client.post(
        "/api/runs",
        json={"scenario_id": "m8_high_backend_workload", "strategy": "fixed"},
    )
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    run_data = _wait_for_completion(run_id)

    assert run_data["status"] == "completed"
    assert run_data["strategy"] == "fixed"
    assert run_data["adaptive_decisions"] == []
    backend_ids = {a["agent_id"] for a in run_data["agents"] if a["role"] == "backend"}
    assert backend_ids == {"BACKEND-1"}
    assert run_data["metrics"]["adaptive"]["spawn_events"] == 0


def test_run_ids_are_unique() -> None:
    first = client.post(
        "/api/runs",
        json={"scenario_id": "m8_low_workload", "strategy": "fixed"},
    ).json()["run_id"]
    second = client.post(
        "/api/runs",
        json={"scenario_id": "m8_low_workload", "strategy": "fixed"},
    ).json()["run_id"]
    assert first != second


def test_run_invalid_scenario() -> None:
    res = client.post(
        "/api/runs",
        json={"scenario_id": "nonexistent_scenario", "strategy": "fixed"},
    )
    assert res.status_code == 400


def test_run_invalid_strategy() -> None:
    res = client.post(
        "/api/runs",
        json={"scenario_id": "m8_low_workload", "strategy": "turbo"},
    )
    assert res.status_code == 422


def test_unknown_run_returns_404() -> None:
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.get("/api/runs/does-not-exist/events").status_code == 404
    assert client.get("/api/runs/does-not-exist/metrics").status_code == 404


def test_api_responses_contain_no_secrets() -> None:
    res = client.post(
        "/api/runs",
        json={"scenario_id": "m8_low_workload", "strategy": "adaptive"},
    )
    run_id = res.json()["run_id"]
    _wait_for_completion(run_id)

    payloads = [
        res.text,
        json.dumps(client.get(f"/api/runs/{run_id}").json()),
        json.dumps(client.get(f"/api/runs/{run_id}/events").json()),
        json.dumps(client.get(f"/api/runs/{run_id}/metrics").json()),
    ]
    for payload in payloads:
        lowered = payload.lower()
        assert "gemini_api_key" not in lowered
        assert "api_key" not in lowered
        assert "aq.ab8rn6" not in lowered


def test_run_storage_is_ephemeral_in_memory() -> None:
    assert isinstance(RUNS, dict)
