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
    monkeypatch.setattr(builds, "SMOKE_TEST", False)
    monkeypatch.setattr(builds, "_make_llm", lambda: FakeLLM(delay=0.01))
    yield
    for build_id in list(builds.SITES):
        builds._stop_site(build_id)
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
    # Slow the fake model so progress spans several 0.4 s polls (updates are coalesced).
    builds._make_llm = lambda: FakeLLM(delay=0.25)  # the fixture restores the original
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


# ---- running the generated site ----------------------------------------------


def test_generated_site_can_be_launched_served_and_stopped():
    import urllib.request

    build_id = _start()
    _wait(build_id)
    assert client.get(f"/api/builds/{build_id}/launch").json() == {"running": False, "url": None, "docs_url": None}

    launched = client.post(f"/api/builds/{build_id}/launch")
    assert launched.status_code == 200, launched.text
    url = launched.json()["url"]
    assert launched.json()["running"] and url.startswith("http://127.0.0.1:")
    assert client.post(f"/api/builds/{build_id}/launch").json()["url"] == url  # idempotent

    page = urllib.request.urlopen(url, timeout=5).read().decode()
    assert "<script" in page                                              # the generated frontend
    assert json.loads(urllib.request.urlopen(url + "api/items", timeout=5).read()) == []  # its backend

    stopped = client.delete(f"/api/builds/{build_id}/launch").json()
    assert stopped == {"running": False, "url": None, "docs_url": None}
    with pytest.raises(Exception):
        urllib.request.urlopen(url, timeout=1)


def test_launch_is_refused_while_building_or_without_a_backend(tmp_path):
    slow = FakeLLM(delay=0.3)
    builds._make_llm = lambda: slow
    build_id = _start()
    assert client.post(f"/api/builds/{build_id}/launch").status_code == 409
    _wait(build_id)

    builds.BUILDS[build_id]["out_dir"] = tmp_path / "empty"
    assert client.post(f"/api/builds/{build_id}/launch").status_code == 400
    assert client.post("/api/builds/nope/launch").status_code == 404


def test_launched_site_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-secret")
    monkeypatch.setenv("SOME_TOKEN", "t")
    monkeypatch.setenv("PYTHONPATH", "src")
    env = builds._site_env()
    assert "GEMINI_API_KEY" not in env and "SOME_TOKEN" not in env and "PYTHONPATH" not in env
    assert "PATH" in env or "Path" in env


# ---- project types -----------------------------------------------------------

from tests.test_profiles import ProfileLLM  # noqa: E402


def _start_type(key, **extra):
    builds._make_llm = lambda: ProfileLLM(key)  # the autouse fixture restores the original
    response = client.post("/api/builds", json={
        "description": f"A {key} project to try out", "strategy": "fixed", "project_type": key, **extra})
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def test_profiles_are_listed_for_the_dashboard():
    profiles = client.get("/api/build-profiles").json()
    assert {p["key"] for p in profiles} == {"web", "api", "cli", "library", "data", "database", "game", "automation"}
    assert all(p["label"] and p["example"] and "runnable" in p for p in profiles)
    assert next(p for p in profiles if p["key"] == "api")["runnable"] == "api"
    assert next(p for p in profiles if p["key"] == "cli")["runnable"] == ""


def test_unknown_project_type_is_rejected():
    response = client.post("/api/builds", json={"description": DESCRIPTION, "project_type": "mobile"})
    assert response.status_code == 422


def test_a_command_line_project_is_built_and_described_in_the_state():
    data = _wait(_start_type("cli"))
    assert data["status"] == "completed" and data["success"] is True
    assert data["project_type"] == "cli" and data["project_label"] == "Command-line tool"
    assert data["has_tests"] is True and data["runnable"] == "" and data["package"] == "app"
    paths = {f["path"]: f["area"] for f in data["files"]}
    assert paths["app/cli.py"] == "source" and paths["tests/test_cli.py"] == "tests"
    assert paths["README.md"] == "project" and paths["docs/architecture.md"] == "docs"
    assert not any("__pycache__" in p or p.endswith(".pyc") for p in paths)


def test_any_generated_file_can_be_read_but_bookkeeping_files_cannot():
    build_id = _start_type("cli")
    _wait(build_id)
    body = client.get(f"/api/builds/{build_id}/files/app/cli.py").json()
    assert "argparse" in body["content"]
    assert client.get(f"/api/builds/{build_id}/files/tests/test_cli.py").status_code == 200
    assert client.get(f"/api/builds/{build_id}/files/ekatra-run.json").status_code == 404


def test_the_projects_own_tests_can_be_run_from_the_api():
    build_id = _start_type("cli")
    _wait(build_id)
    result = client.post(f"/api/builds/{build_id}/tests").json()
    assert result["ok"] is True and result["exit_code"] == 0 and "passed" in result["output"]


def test_the_demo_command_can_be_run_from_the_api():
    build_id = _start_type("game")
    _wait(build_id)
    result = client.post(f"/api/builds/{build_id}/demo").json()
    assert result["ok"] is True and result["results"][0]["command"].startswith("python -m app")


def test_tests_and_demo_are_refused_when_they_do_not_apply():
    web = _start()
    _wait(web)
    assert client.post(f"/api/builds/{web}/tests").status_code == 400
    assert client.post(f"/api/builds/{web}/demo").status_code == 400
    service = _start_type("api")
    _wait(service)
    assert client.post(f"/api/builds/{service}/demo").status_code == 400  # a server: use Run site, not a demo
    assert client.post(f"/api/builds/{service}/tests").json()["ok"] is True
    library = _start_type("library")
    _wait(library)
    assert client.post(f"/api/builds/{library}/demo").json()["ok"] is True  # the import check
    assert client.post("/api/builds/nope/tests").status_code == 404


def test_only_servers_can_be_launched():
    build_id = _start_type("cli")
    _wait(build_id)
    response = client.post(f"/api/builds/{build_id}/launch")
    assert response.status_code == 400 and "no server" in response.json()["detail"]


def test_an_api_project_can_be_launched_and_exposes_its_docs():
    import urllib.request

    build_id = _start_type("api")
    _wait(build_id)
    launched = client.post(f"/api/builds/{build_id}/launch")
    assert launched.status_code == 200, launched.text
    info = launched.json()
    assert info["docs_url"] == info["url"] + "docs"
    assert json.loads(urllib.request.urlopen(info["url"] + "api/items", timeout=5).read()) == []
    assert b"swagger" in urllib.request.urlopen(info["docs_url"], timeout=5).read().lower()
    assert client.delete(f"/api/builds/{build_id}/launch").json()["running"] is False
