"""API tests for change requests and for projects restored from disk after a restart."""

import json
import time

from ekatra.api import builds
from tests.test_api_builds import _isolated_builds, _wait, client  # noqa: F401  (autouse fixture)
from tests.test_change import REQUEST, ChangeLLM
from tests.test_profiles import ProfileLLM

BROKEN_CORE = {"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"}


class SlowLLM(ProfileLLM):
    def __call__(self, prompt, json_mode):
        time.sleep(0.3)
        return super().__call__(prompt, json_mode)


def _build_cli(llm=None, **extra):
    builds._make_llm = lambda: llm or ProfileLLM("cli")  # the autouse fixture restores the original
    response = client.post("/api/builds", json={
        "description": "A to-do command-line tool", "strategy": "fixed", "project_type": "cli", **extra})
    assert response.status_code == 200, response.text
    build_id = response.json()["run_id"]
    assert _wait(build_id)["status"] == "completed"
    return build_id


def _change(build_id, request=REQUEST, llm=None):
    builds._make_llm = lambda: llm or ChangeLLM()
    response = client.post(f"/api/builds/{build_id}/changes", json={"request": request})
    assert response.status_code == 200, response.text
    return _wait(build_id)


# ---- changing a finished build -----------------------------------------------------------


def test_a_change_request_modifies_the_finished_project():
    build_id = _build_cli()
    data = _change(build_id)
    assert data["status"] == "completed" and data["success"] is True and data["change_error"] is None
    assert [c["request"] for c in data["changes"]] == [REQUEST]
    assert [t["role"] for t in data["tasks"]] == ["backend", "qa"] and data["plan_source"] == "change"
    assert {"app/core.py", "tests/test_remove.py"} <= {f["path"] for f in data["files"]}
    assert "def remove" in client.get(f"/api/builds/{build_id}/files/app/core.py").json()["content"]
    assert any(line.startswith("---- Change request:") for line in data["log"])
    assert data["project_type"] == "cli" and data["package"] == "app"


def test_the_changed_project_still_passes_its_own_tests():
    build_id = _build_cli()
    _change(build_id)
    result = client.post(f"/api/builds/{build_id}/tests").json()
    assert result["ok"] is True and "passed" in result["output"]


def test_a_second_change_is_recorded_after_the_first():
    build_id = _build_cli()
    _change(build_id)
    plan = {"tasks": [{"key": "helper", "role": "backend", "description": "helper", "dependencies": [],
                       "deliverables": ["app/helpers2.py"]}]}
    data = _change(build_id, request="Add a helper module", llm=ChangeLLM(plan=plan))
    assert [c["request"] for c in data["changes"]] == [REQUEST, "Add a helper module"]
    assert "app/helpers2.py" in {f["path"] for f in data["files"]}


def test_a_change_cannot_start_while_another_build_is_running():
    first = _build_cli()
    builds._make_llm = lambda: SlowLLM("cli")
    started = client.post("/api/builds", json={"description": "Another slow tool", "project_type": "cli"})
    assert started.status_code == 200
    builds._make_llm = lambda: ChangeLLM()
    refused = client.post(f"/api/builds/{first}/changes", json={"request": REQUEST})
    assert refused.status_code == 409 and "already running" in refused.json()["detail"]


def test_an_empty_request_is_refused_when_there_is_nothing_to_fix():
    build_id = _build_cli()
    response = client.post(f"/api/builds/{build_id}/changes", json={})
    assert response.status_code == 400 and "no issues to fix" in response.json()["detail"]


def test_with_no_request_the_run_repairs_the_issues_a_build_ended_with(monkeypatch):
    monkeypatch.setattr(builds, "SMOKE_TEST", True)  # the runtime checks are what find the failing test
    build_id = _build_cli(llm=ProfileLLM("cli", broken=BROKEN_CORE), repair_rounds=0)
    broken = client.get(f"/api/builds/{build_id}").json()
    assert broken["success"] is False and broken["final_issues"]
    builds._make_llm = lambda: ProfileLLM("cli")
    assert client.post(f"/api/builds/{build_id}/changes", json={}).status_code == 200
    data = _wait(build_id)
    assert data["success"] is True and data["final_issues"] == []
    assert data["changes"][-1]["request"] == "(fix remaining issues)" and data["plan_source"] == "repair"


def test_an_unplannable_change_explains_why_and_leaves_the_project_as_it_was():
    build_id = _build_cli()
    before = client.get(f"/api/builds/{build_id}").json()
    data = _change(build_id, llm=ChangeLLM(plan={"tasks": [], "reason": "this needs a GUI toolkit"}))
    assert data["status"] == "completed" and data["success"] is True
    assert "this needs a GUI toolkit" in data["change_error"]
    assert len(data["tasks"]) == len(before["tasks"]) and data["plan_source"] == before["plan_source"]
    assert "tests/test_remove.py" not in {f["path"] for f in data["files"]}
    assert any("could not be applied" in line for line in data["log"])


def test_change_request_validation():
    build_id = _build_cli()
    assert client.post("/api/builds/nope/changes", json={"request": REQUEST}).status_code == 404
    assert client.post(f"/api/builds/{build_id}/changes", json={"request": "x" * 601}).status_code == 422


def test_a_change_needs_an_api_key_when_using_gemini():
    build_id = _build_cli()
    builds._make_llm = lambda: None
    response = client.post(f"/api/builds/{build_id}/changes", json={"request": REQUEST})
    assert response.status_code == 400 and "GEMINI_API_KEY" in response.json()["detail"]


# ---- projects survive a restart ------------------------------------------------------------


def test_finished_projects_are_restored_from_disk_and_can_still_be_changed():
    original = _build_cli()
    builds.BUILDS.clear()  # what a server restart does
    assert builds.load_builds_from_disk() == 1
    restored_id = next(iter(builds.BUILDS))
    assert restored_id != original and restored_id.startswith("disk-")
    assert [b["run_id"] for b in client.get("/api/builds").json()] == [restored_id]

    data = client.get(f"/api/builds/{restored_id}").json()
    assert data["status"] == "completed" and data["success"] is True
    assert data["project_type"] == "cli" and data["package"] == "app" and data["description"]
    assert {"app/cli.py", "tests/test_cli.py"} <= {f["path"] for f in data["files"]}
    assert builds.load_builds_from_disk() == 0, "loading twice must not duplicate"

    changed = _change(restored_id)
    assert changed["success"] is True and "tests/test_remove.py" in {f["path"] for f in changed["files"]}

    builds.BUILDS.clear()
    builds.load_builds_from_disk()
    again = client.get(f"/api/builds/{next(iter(builds.BUILDS))}").json()
    assert [c["request"] for c in again["changes"]] == [REQUEST]
    assert [t["role"] for t in again["tasks"]] == ["backend", "qa"], "the latest run's tasks are shown"


def test_only_real_projects_with_safe_folder_names_are_restored(tmp_path):
    (tmp_path / "empty-folder").mkdir()
    (tmp_path / "unsafe name").mkdir()
    (tmp_path / "unsafe name" / "ekatra-run.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "ekatra-run.json").write_text("not json", encoding="utf-8")
    (tmp_path / "old-web-build").mkdir()
    (tmp_path / "old-web-build" / "ekatra-run.json").write_text(json.dumps({
        "project_description": "An old site", "strategy": "adaptive",
        "tasks": [{"id": "TASK-1", "role": "backend", "status": "COMPLETED"}],
        "config": {}, "final_issues": [{"severity": "medium"}],
    }), encoding="utf-8")
    assert builds.load_builds_from_disk() == 1
    entry = builds.BUILDS["disk-old-web-build"]
    assert entry["project_type"] == "web" and entry["success"] is True and entry["description"] == "An old site"
