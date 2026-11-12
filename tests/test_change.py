"""Tests for change requests: modifying a project that was already built."""

import json
import re

import pytest

from ekatra.build import BuildConfig, PlanError, validate_plan
from ekatra.build.change import MAX_REQUEST_CHARS, change_project, infer_owners, plan_change
from ekatra.build.profiles import get_profile
from tests.test_profiles import GOOD, ProfileLLM, _build

REQUEST = "Add a remove function that deletes an item from the list"
CORE_WITH_REMOVE = (
    "def add(items, text):\n    items.append(text)\n    return items\n\n\n"
    "def remove(items, text):\n    items.remove(text)\n    return items\n"
)
REMOVE_TEST = "from app.core import remove\n\n\ndef test_remove():\n    assert remove(['a', 'b'], 'a') == ['b']\n"
CHANGE_PLAN = {"tasks": [
    {"key": "core_change", "role": "backend", "description": "Add remove(items, text) to app/core.py",
     "dependencies": [], "deliverables": ["app/core.py"]},
    {"key": "remove_tests", "role": "qa", "description": "Test remove()", "dependencies": ["core_change"],
     "deliverables": ["tests/test_remove.py"]},
]}


class ChangeLLM(ProfileLLM):
    """Answers change-planning prompts and change tasks; everything else like a normal build."""

    def __init__(self, key="cli", plan=None, broken=None):
        super().__init__(key)
        self.plan = CHANGE_PLAN if plan is None else plan
        self.changed = {"app/core.py": CORE_WITH_REMOVE, "tests/test_remove.py": REMOVE_TEST,
                        "app/helpers2.py": "VALUE = 1\n"}
        self.broken_change = broken or {}
        self.change_prompts = []

    def __call__(self, prompt, json_mode):
        if "The user now asks for this CHANGE" in prompt:
            self.calls.append(prompt)
            return json.dumps(self.plan)
        match = re.search(r"exactly these files \(and no others\): (.*)", prompt)
        if match and "CHANGE REQUEST from the user" in prompt:
            self.calls.append(prompt)
            self.change_prompts.append(prompt)
            files = []
            for path in match.group(1).split(", "):
                if path in self.broken_change and "FIX task" not in prompt:
                    content = self.broken_change[path]
                else:
                    content = self.changed.get(path) or self.content(path, prompt)
                files.append({"path": path, "content": content})
            return json.dumps({"files": files, "summary": "changed"})
        return super().__call__(prompt, json_mode)


BROKEN_ADD = {"app/core.py": (
    "def add(items, text):\n    raise RuntimeError('boom')\n\n\n"
    "def remove(items, text):\n    items.remove(text)\n    return items\n")}


def _project(tmp_path, **cfg):
    return _build(tmp_path, "cli", **cfg)


def _change(result, request=REQUEST, llm=None, **cfg):
    return change_project(
        result.root, request, project_type="cli", package="app", description="A to-do tool", strategy="fixed",
        llm=llm or ChangeLLM(), config=BuildConfig(**cfg),
    )


# ---- planning ------------------------------------------------------------------------


def test_a_change_plan_need_not_contain_every_role_or_the_entry_files():
    tasks = validate_plan(CHANGE_PLAN, get_profile("cli"), "app", strict=False)
    assert [t.key for t in tasks] == ["core_change", "remove_tests"]
    with pytest.raises(PlanError, match="no frontend task|no architect task|must deliver"):
        validate_plan(CHANGE_PLAN, get_profile("cli"), "app")  # a full build plan still needs them


@pytest.mark.parametrize("mutate,message", [
    (lambda p: p["tasks"][1].update(role="backend", deliverables=["app/core.py"]), "owned by both"),
    (lambda p: p["tasks"][0].update(deliverables=["tests/test_x.py"]), "may only write"),
    (lambda p: p["tasks"][1].update(dependencies=["nope"]), "unknown"),
    (lambda p: p["tasks"][0].update(role="designer"), "unsupported role"),
])
def test_change_plans_obey_the_same_ownership_and_location_rules(mutate, message):
    plan = json.loads(json.dumps(CHANGE_PLAN))
    mutate(plan)
    with pytest.raises(PlanError, match=message):
        validate_plan(plan, get_profile("cli"), "app", strict=False)


def test_the_prompt_carries_the_request_the_files_and_the_architecture():
    seen = []

    def llm(prompt, json_mode):
        seen.append(prompt)
        return json.dumps(CHANGE_PLAN)

    plan_change(REQUEST, llm, get_profile("cli"), "app", "A to-do tool",
                [("app/core.py", 120), ("tests/test_cli.py", 80)], "# Arch\nadd and list")
    prompt = seen[0]
    assert REQUEST in prompt and "app/core.py (120)" in prompt and "add and list" in prompt and "A to-do tool" in prompt
    assert "backend: app/, data/" in prompt and "qa: tests/, docs/" in prompt
    assert "<<" not in prompt


def test_an_impossible_request_surfaces_the_managers_reason_without_retrying():
    calls = []

    def llm(prompt, json_mode):
        calls.append(1)
        return json.dumps({"tasks": [], "reason": "this needs a GUI toolkit"})

    with pytest.raises(PlanError, match="this needs a GUI toolkit"):
        plan_change(REQUEST, llm, get_profile("cli"), "app", "", [("app/core.py", 1)], "")
    assert len(calls) == 1


def test_an_unusable_reply_is_retried_once_and_then_reported():
    calls = []

    def llm(prompt, json_mode):
        calls.append(1)
        return "not json"

    with pytest.raises(PlanError, match="Could not plan the change"):
        plan_change(REQUEST, llm, get_profile("cli"), "app", "", [("app/core.py", 1)], "")
    assert len(calls) == 2


def test_owners_are_inferred_for_projects_whose_plan_was_not_saved():
    cli = infer_owners(["app/core.py", "tests/test_cli.py", "docs/architecture.md", "docs/qa-report.md",
                        "docs/security-report.md", "data/sample.csv", "README.md"], get_profile("cli"), "app")
    assert cli == {"app/core.py": "backend", "tests/test_cli.py": "qa", "docs/architecture.md": "architect",
                   "docs/qa-report.md": "qa", "docs/security-report.md": "security", "data/sample.csv": "backend"}
    web = infer_owners(["backend/main.py", "frontend/app.js", "docs/architecture.md"], get_profile("web"), "")
    assert web == {"backend/main.py": "backend", "frontend/app.js": "frontend", "docs/architecture.md": "architect"}


# ---- applying a change -----------------------------------------------------------------


def test_a_change_rewrites_the_assigned_files_and_the_project_still_passes_its_tests(tmp_path):
    built = _project(tmp_path)
    llm = ChangeLLM()
    result = _change(built, llm=llm)
    assert result.success and result.final_issues == [] and result.plan_source == "change"
    assert "def remove" in (built.root / "app/core.py").read_text()
    assert (built.root / "tests/test_remove.py").is_file()
    assert (built.root / "app/cli.py").read_text() == GOOD["app/cli.py"], "files outside the plan are untouched"
    assert [t["role"] for t in result.state["tasks"]] == ["backend", "qa"]


def test_the_developer_is_shown_the_request_and_the_current_file(tmp_path):
    built = _project(tmp_path)
    llm = ChangeLLM()
    _change(built, llm=llm)
    prompt = next(p for p in llm.change_prompts if "app/core.py" in p.split("exactly these files")[1][:40])
    assert "CHANGE REQUEST from the user: " + REQUEST in prompt
    assert "Rewrite each file listed below COMPLETELY" in prompt
    assert "def add(items, text):" in prompt, "the existing file content is provided so nothing is lost"


def test_a_change_that_breaks_a_test_is_repaired_by_the_normal_loop(tmp_path):
    built = _project(tmp_path)
    llm = ChangeLLM(broken=BROKEN_ADD)
    result = _change(built, llm=llm, repair_rounds=2)
    assert any(t["description"].startswith("Fix review findings") for t in result.state["tasks"])
    assert result.success and "def remove" in (built.root / "app/core.py").read_text()


def test_without_repair_a_breaking_change_is_reported_not_hidden(tmp_path):
    built = _project(tmp_path)
    llm = ChangeLLM(broken=BROKEN_ADD)
    result = _change(built, llm=llm, repair_rounds=0)
    assert not result.success and any("boom" in i["description"] for i in result.final_issues)


def test_each_change_is_recorded_in_its_own_numbered_file(tmp_path):
    built = _project(tmp_path)
    _change(built)
    _change(built, request="Add another small helper", llm=ChangeLLM(plan={"tasks": [
        {"key": "helper", "role": "backend", "description": "helper", "dependencies": [], "deliverables": ["app/helpers2.py"]}]}))
    first = json.loads((built.root / "ekatra-change-1.json").read_text())
    assert first["change_request"] == REQUEST and first["change_number"] == 1 and first["config"]["package"] == "app"
    assert json.loads((built.root / "ekatra-change-2.json").read_text())["change_number"] == 2
    assert (built.root / "ekatra-run.json").is_file(), "the original build record is kept"


def test_a_change_run_can_only_write_where_each_role_is_allowed(tmp_path):
    built = _project(tmp_path)
    escape = {"tasks": [{"key": "evil", "role": "qa", "description": "x", "dependencies": [],
                         "deliverables": ["app/core.py"]}]}
    with pytest.raises(PlanError, match="may only write"):
        _change(built, llm=ChangeLLM(plan=escape))


# ---- fix-only runs and guards ----------------------------------------------------------


def test_with_no_request_the_run_only_rechecks_and_repairs(tmp_path):
    broken = ProfileLLM("cli", broken={"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"})
    built = _project(tmp_path, llm=broken, repair_rounds=0)
    assert not built.success
    result = change_project(built.root, None, project_type="cli", package="app", strategy="fixed",
                            llm=ProfileLLM("cli"), config=BuildConfig(repair_rounds=2))
    assert result.success and result.plan_source == "repair" and result.final_issues == []
    assert "boom" not in (built.root / "app/core.py").read_text()
    assert (built.root / "ekatra-change-1.json").is_file()


def test_an_import_error_blames_the_module_that_should_define_the_name_as_well_as_the_test(tmp_path):
    from ekatra.build import pychecks

    for path, text in {"app/__init__.py": "", "app/cli.py": "", "app/__main__.py": "print('hi')\n",
                       "app/core.py": "def add(items, text):\n    return items\n",
                       "tests/test_core.py": "from app.core import remove\n\n\ndef test_remove():\n    assert remove\n"}.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    owners = {"app/core.py": "backend", "tests/test_core.py": "qa"}
    issues = pychecks.runtime_check(tmp_path, "app", get_profile("cli"), owners)
    assert {(i["owner"], i["file"]) for i in issues} == {("qa", "tests/test_core.py"), ("backend", "app/core.py")}
    assert any("Define it there" in i["description"] for i in issues)


def test_nothing_to_change_in_an_empty_folder_and_overlong_requests_are_refused(tmp_path):
    with pytest.raises(ValueError, match="nothing to change"):
        change_project(tmp_path / "empty", REQUEST, project_type="cli", package="app", llm=ChangeLLM())
    built = _project(tmp_path)
    with pytest.raises(ValueError, match="longer than"):
        change_project(built.root, "x" * (MAX_REQUEST_CHARS + 1), project_type="cli", package="app", llm=ChangeLLM())
