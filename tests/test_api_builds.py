"""Tests for the real-build REST/SSE endpoints (fake LLM, no network)."""

import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ekatra.api import builds
from ekatra.api.app import app
from ekatra.api.summary import workload_and_risk
from ekatra.experiments import high_backend_workload
from ekatra.experiments.runner import build_initial_state
from tests.test_build import FakeLLM

client = TestClient(app)
DESCRIPTION = "A tiny shop website with a product list"


@pytest.fixture(autouse=True)
def _isolated_builds(tmp_path, monkeypatch):
    builds.BUILDS.clear()
    monkeypatch.setattr(builds, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(builds, "_make_llm", lambda: FakeLLM(delay=0.01))
    yield
    deadline = time.time() + 20
    while any(b["status"] == "running" for b in builds.BUILDS.values()) and time.time() < deadline:
        time.sleep(0.05)
    builds.BUILDS.clear()


def _start(**extra):
    response = client.post("/api/builds", json={"description": DESCRIPTION, "strategy": "adaptive", **extra})
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _wait(build_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/builds/{build_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("build did not finish")


def test_build_runs_end_to_end_and_exposes_dashboard_shaped_state():
    data = _wait(_start())
    assert data["status"] == "completed" and data["success"] is True
    assert data["scenario_id"] == "live_build" and data["plan_source"] == "llm"
    assert len(data["tasks"]) == 11 and all(t["status"] == "COMPLETED" for t in data["tasks"])
    assert {a["agent_id"] for a in data["agents"]} >= {"ARCH-1", "BACKEND-1", "FRONTEND-1"}
    assert data["metrics"]["task"]["completed_tasks"] == 11
    assert any(e["type"] == "workflow_completed" for e in data["observability_events"])
    paths = {f["path"] for f in data["files"]}
    assert {"backend/main.py", "frontend/index.html", "docs/architecture.md", "README.md"} <= paths
    assert data["log"] and data["out_dir"]
    assert set(data["workload"]) >= {"score", "level", "queueLength", "complexity", "executionDelay", "failureRate"}
    assert set(data["risk"]) >= {"score", "level", "securityFindings", "highRiskTasks"}


def test_state_is_published_while_the_build_runs():
    build_id = _start()
    seen = set()
    deadline = time.time() + 30
    while time.time() < deadline:
        data = client.get(f"/api/builds/{build_id}").json()
        seen.add(sum(1 for t in data["tasks"] if t["status"] == "COMPLETED"))
        if data["status"] != "running":
            break
        time.sleep(0.01)
    assert len(seen) > 2, "expected to observe intermediate progress"


def test_sse_stream_pushes_updates_then_done():
    build_id = _start()
    updates, done = [], False
    with client.stream("GET", f"/api/builds/{build_id}/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        event = ""
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event != "done":
                updates.append(json.loads(line[5:]))
            elif line.startswith("data:") and event == "done":
                done = True
                break
    assert done and len(updates) >= 3
    assert updates[-1]["status"] == "completed" and len(updates[-1]["files"]) >= 5
    versions = [u["version"] for u in updates]
    assert versions == sorted(versions)


def test_only_one_build_may_run_at_a_time():
    slow = FakeLLM(delay=0.3)
    builds._make_llm = lambda: slow  # monkeypatch fixture restores the original
    _start()
    second = client.post("/api/builds", json={"description": DESCRIPTION})
    assert second.status_code == 409


def test_start_requires_an_api_key_when_using_gemini(monkeypatch):
    monkeypatch.setattr(builds, "_make_llm", lambda: None)
    response = client.post("/api/builds", json={"description": DESCRIPTION})
    assert response.status_code == 400 and "GEMINI_API_KEY" in response.json()["detail"]


def test_request_validation():
    assert client.post("/api/builds", json={"description": "short"}).status_code == 422
    assert client.post("/api/builds", json={"description": DESCRIPTION, "strategy": "x"}).status_code == 422


def test_unknown_build_is_404():
    assert client.get("/api/builds/nope").status_code == 404
    assert client.get("/api/builds/nope/stream").status_code == 404
    assert client.get("/api/builds/nope/files").status_code == 404


def test_files_can_be_listed_and_read():
    build_id = _start()
    _wait(build_id)
    listing = client.get(f"/api/builds/{build_id}/files").json()
    assert "backend/main.py" in {f["path"] for f in listing}
    body = client.get(f"/api/builds/{build_id}/files/backend/main.py").json()
    assert "FastAPI" in body["content"] and body["truncated"] is False
    assert client.get(f"/api/builds/{build_id}/files/backend/missing.py").status_code == 404
    assert client.get(f"/api/builds/{build_id}/files/ekatra-run.json").status_code == 404


def test_file_endpoint_cannot_escape_the_project_folder():
    build_id = _start()
    _wait(build_id)
    for bad in ("../secret.txt", "..", ".env"):
        with pytest.raises(HTTPException) as info:
            builds.read_build_file(build_id, bad)
        assert info.value.status_code == 404
    with pytest.raises(HTTPException) as info:
        builds.read_build_file(build_id, "backend/../../../outside.txt")
    assert info.value.status_code == 400


def test_failed_build_reports_an_error(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(builds, "build_project", broken)
    data = _wait(_start())
    assert data["status"] == "failed" and "boom" in data["error"]


def test_builds_are_listed_newest_first():
    first = _start()
    _wait(first)
    second = _start()
    _wait(second)
    assert [b["run_id"] for b in client.get("/api/builds").json()][:2] == [second, first]


def test_workload_summary_uses_real_scores_not_constants():
    state = build_initial_state(high_backend_workload())
    workload, risk = workload_and_risk(state)
    assert workload["score"] > 60 and workload["level"] in ("ELEVATED", "HIGH")
    assert workload["complexity"] != 0.42 and 0 < workload["complexity"] <= 1
    assert 0 <= risk["score"] <= 100
