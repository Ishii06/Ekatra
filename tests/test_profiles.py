"""Tests for the project profiles: API, CLI, library, data, database, game, automation."""

import dataclasses
import json
import re
from pathlib import Path

import pytest

from ekatra.build import BuildConfig, PlanError, build_project, plan_project, validate_plan
from ekatra.build import pychecks
from ekatra.build.plan import fallback_package, plan_project_full, resolve_package, valid_package
from ekatra.build.profiles import PROFILES, get_profile
from ekatra.tools.registry import ALLOWED_TOOLS, RoleToolPolicy

PYTHON_KEYS = [k for k, p in PROFILES.items() if p.kind == "python"]

GOOD = {
    "docs/architecture.md": "# Architecture\n",
    # api
    "app/store.py": "ITEMS = []\n",
    "app/main.py": ("from fastapi import FastAPI\n\nfrom app.store import ITEMS\n\napp = FastAPI()\n\n\n"
                    "@app.get('/api/items')\ndef list_items():\n    return ITEMS\n"),
    "tests/test_api.py": ("from fastapi.testclient import TestClient\n\nfrom app.main import app\n\n\n"
                          "def test_items():\n    assert TestClient(app).get('/api/items').json() == []\n"),
    # cli
    "app/core.py": "def add(items, text):\n    items.append(text)\n    return items\n",
    "app/cli.py": ("import argparse\n\nfrom app.core import add\n\n\ndef main(argv=None):\n"
                   "    parser = argparse.ArgumentParser(prog='app')\n    parser.add_argument('--text', default='x')\n"
                   "    args = parser.parse_args(argv)\n    print(add([], args.text))\n    return 0\n"),
    "tests/test_cli.py": "from app.cli import main\n\n\ndef test_main():\n    assert main(['--text', 'a']) == 0\n",
    # library
    "app/helpers.py": "def clean(text):\n    return text.strip()\n",
    "tests/test_core.py": ("from app import clean, slugify\n\n\ndef test_slugify():\n    assert slugify('A B') == 'a-b'\n\n\n"
                           "def test_clean():\n    assert clean(' x ') == 'x'\n"),
    # data
    "data/sample.csv": "name,score\na,1\nb,3\nc,5\nd,7\ne,2\nf,4\ng,6\nh,8\nbad,x\n",
    "app/analysis.py": ("import csv\n\n\ndef summarize(path):\n    rows = []\n    with open(path, newline='') as handle:\n"
                        "        for row in csv.DictReader(handle):\n            try:\n"
                        "                rows.append(int(row['score']))\n            except ValueError:\n"
                        "                continue\n    return {'count': len(rows), 'total': sum(rows)}\n"),
    "app/report.py": "import json\n\n\ndef write(summary, path):\n    with open(path, 'w') as handle:\n        json.dump(summary, handle)\n",
    "tests/test_analysis.py": ("from app.analysis import summarize\n\n\ndef test_summarize(tmp_path):\n"
                               "    path = tmp_path / 'd.csv'\n    path.write_text('name,score\\na,2\\nb,x\\n')\n"
                               "    assert summarize(path) == {'count': 1, 'total': 2}\n"),
    # database
    "app/db.py": ("import sqlite3\n\n\ndef connect():\n    conn = sqlite3.connect(':memory:')\n"
                  "    conn.execute('create table t(id integer primary key, name text)')\n    return conn\n\n\n"
                  "def add(conn, name):\n    conn.execute('insert into t(name) values (?)', (name,))\n"
                  "    return conn.execute('select count(*) from t').fetchone()[0]\n"),
    "tests/test_db.py": "from app.db import add, connect\n\n\ndef test_add():\n    assert add(connect(), 'x') == 1\n",
    # game
    "app/game.py": ("class Game:\n    def __init__(self):\n        self.score = 0\n\n"
                    "    def play(self, command):\n        self.score += 1\n        return self.score\n"),
    "tests/test_game.py": "from app.game import Game\n\n\ndef test_play():\n    assert Game().play('look') == 1\n",
    # automation
    "app/organizer.py": "import pathlib\n\n\ndef plan(target):\n    return sorted(p.name for p in pathlib.Path(target).iterdir())\n",
    "tests/test_organizer.py": ("from app.organizer import plan\n\n\ndef test_plan(tmp_path):\n"
                                 "    (tmp_path / 'a.txt').write_text('x')\n    assert plan(tmp_path) == ['a.txt']\n"),
}
MAINS = {
    "cli": "from app.cli import main\n\nraise SystemExit(main())\n",
    "data": ("import pathlib\n\nfrom app.analysis import summarize\nfrom app.report import write\n\n\ndef main():\n"
             "    out = pathlib.Path('output')\n    out.mkdir(exist_ok=True)\n"
             "    write(summarize('data/sample.csv'), out / 'summary.json')\n\n\nif __name__ == '__main__':\n    main()\n"),
    "database": "from app.db import add, connect\n\nif __name__ == '__main__':\n    print(add(connect(), 'x'))\n",
    "game": ("import sys\n\nfrom app.game import Game\n\n\ndef main():\n    game = Game()\n    for line in sys.stdin:\n"
             "        if line.strip() == 'quit':\n            break\n        print(game.play(line.strip()))\n\n\n"
             "if __name__ == '__main__':\n    main()\n"),
    "automation": ("import argparse\n\nfrom app.organizer import plan\n\n\ndef main(argv=None):\n"
                   "    parser = argparse.ArgumentParser(prog='app')\n    parser.add_argument('--target', default='.')\n"
                   "    parser.add_argument('--dry-run', action='store_true')\n    parser.add_argument('--apply', action='store_true')\n"
                   "    args = parser.parse_args(argv)\n    print(plan(args.target))\n    return 0\n\n\n"
                   "if __name__ == '__main__':\n    raise SystemExit(main())\n"),
}
INITS = {"library": "from app.core import slugify\nfrom app.helpers import clean\n"}
CORE_LIBRARY = "def slugify(text):\n    return text.lower().replace(' ', '-')\n"


class ProfileLLM:
    """Scripted model that answers every prompt kind for one project type."""

    def __init__(self, key, broken=None):
        self.key = key
        self.broken = broken or {}
        self.calls = []

    def content(self, path, prompt):
        if path in self.broken and "FIX task" not in prompt:
            return self.broken[path]
        if path == "app/__main__.py":
            return MAINS[self.key]
        if path == "app/__init__.py":
            return INITS.get(self.key, "")
        if path == "app/core.py" and self.key == "library":
            return CORE_LIBRARY
        return GOOD[path]

    def __call__(self, prompt, json_mode):
        self.calls.append(prompt)
        profile = get_profile(self.key)
        if "Project Manager" in prompt:
            tasks = [dataclasses.asdict(t) for t in profile.fallback("a project", "app")]
            return json.dumps({"package": "app", "tasks": tasks})
        if "software architect" in prompt:
            return json.dumps({"files": [{"path": "docs/architecture.md", "content": "# Architecture\n"}],
                               "summary": "designed"})
        if "reviewing this" in prompt:
            return json.dumps({"report_markdown": "# Report\nok", "issues": [], "summary": "reviewed"})
        wanted = re.search(r"exactly these files \(and no others\): (.*)", prompt).group(1).split(", ")
        files = [{"path": p, "content": self.content(p, prompt)} for p in wanted]
        return json.dumps({"files": files, "summary": "wrote " + wanted[0]})


def _plan_json(key, pkg="app"):
    profile = get_profile(key)
    return {"package": pkg, "tasks": [dataclasses.asdict(t) for t in profile.fallback("a project", pkg)]}


def _write(root, files):
    for path, content in files.items():
        target = Path(root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


# ---- registry ----------------------------------------------------------------


def test_registry_has_the_eight_project_types():
    assert set(PROFILES) == {"web", "api", "cli", "library", "data", "database", "game", "automation"}
    for profile in PROFILES.values():
        assert profile.label and profile.summary and len(profile.example) > 40
        assert profile.public()["key"] == profile.key


def test_unknown_project_type_is_rejected():
    with pytest.raises(ValueError):
        get_profile("mobile")


def test_python_profiles_share_one_layout_with_per_role_write_permissions():
    for key in PYTHON_KEYS:
        profile = get_profile(key)
        assert profile.prefixes_for("backend", "todo") == ("todo/", "data/")
        assert profile.prefixes_for("qa", "todo") == ("tests/", "docs/")
        assert profile.prefixes_for("architect", "todo") == ("docs/",)
        assert "qa" in profile.fixable_roles


def test_qa_may_write_tests_but_not_source_code():
    profile = get_profile("cli")
    policy = RoleToolPolicy("qa", set(ALLOWED_TOOLS["qa"]), profile.prefixes_for("qa", "app"))
    assert policy.allows("write_file", "tests/test_cli.py")
    assert policy.allows("write_file", "docs/qa-report.md")
    assert not policy.allows("write_file", "app/core.py")
    backend = RoleToolPolicy("backend", set(ALLOWED_TOOLS["backend"]), profile.prefixes_for("backend", "app"))
    assert backend.allows("write_file", "app/core.py") and not backend.allows("write_file", "tests/test_x.py")


# ---- planning ----------------------------------------------------------------


@pytest.mark.parametrize("key", list(PROFILES))
def test_every_fallback_plan_is_itself_a_valid_plan(key):
    profile = get_profile(key)
    raw = _plan_json(key) if profile.kind == "python" else {"tasks": [
        dataclasses.asdict(t) for t in profile.fallback("a project", "")]}
    tasks = validate_plan(raw, profile)
    assert tasks and tasks[0].key == "architecture"


def test_the_command_line_plan_the_web_planner_rejected_is_valid_for_the_cli_profile():
    def t(key, role, files, deps=()):
        return {"key": key, "role": role, "description": f"do {key}", "dependencies": list(deps), "deliverables": files}

    plan = {"package": "todo_cli", "tasks": [
        t("architecture", "architect", ["docs/architecture.md"]),
        t("core", "backend", ["todo_cli/__init__.py", "todo_cli/core.py"], ["architecture"]),
        t("cli", "frontend", ["todo_cli/cli.py", "todo_cli/__main__.py"], ["architecture", "core"]),
        t("tests", "qa", ["tests/test_cli.py"], ["cli"]),
        t("qa_report", "qa", ["docs/qa-report.md"], ["tests"]),
        t("security", "security", ["docs/security-report.md"], ["cli"]),
    ]}
    assert len(validate_plan(plan, get_profile("cli"))) == 6
    with pytest.raises(PlanError, match="may only write under backend/"):
        validate_plan(plan, get_profile("web"))  # the website profile only accepts backend/ and frontend/


@pytest.mark.parametrize("mutate,message", [
    (lambda p: p["tasks"][3].update(deliverables=["app/test_cli.py"]), "may only write"),
    (lambda p: p["tasks"][1].update(deliverables=["tests/test_core.py"]), "may only write"),
    (lambda p: p["tasks"].pop(3), "tests"),
    (lambda p: p["tasks"][2].update(deliverables=["app/cli.py"]), "must deliver"),
])
def test_python_plan_rules(mutate, message):
    plan = _plan_json("cli")
    mutate(plan)
    # drop the QA report that depended on the removed task, so only the targeted rule fails
    plan["tasks"] = [t for t in plan["tasks"] if not (t["key"] == "qa_report" and "tests" in t["dependencies"]
                                                      and not any(x["key"] == "tests" for x in plan["tasks"]))]
    with pytest.raises(PlanError, match=message):
        validate_plan(plan, get_profile("cli"))


def test_frontend_role_is_not_allowed_for_profiles_without_one():
    plan = _plan_json("library")
    plan["tasks"][1]["role"] = "frontend"
    with pytest.raises(PlanError, match="unsupported role"):
        validate_plan(plan, get_profile("library"))


def test_package_names_are_validated_and_inferred():
    assert valid_package("todo_cli") and not valid_package("tests") and not valid_package("class")
    assert not valid_package("Bad-Name") and not valid_package("a")
    profile = get_profile("cli")
    assert resolve_package({"package": "todo_cli", "tasks": []}, profile) == "todo_cli"
    assert resolve_package({"package": "tests", "tasks": [{"role": "backend", "deliverables": ["mytool/a.py"]}]},
                           profile) == "mytool"
    assert resolve_package({"tasks": []}, profile) == "app"
    assert resolve_package({"tasks": []}, get_profile("web")) == ""
    name = fallback_package("A command-line inventory manager in Python")
    assert valid_package(name) and name == "inventory_manager"
    assert fallback_package("!!!") == "app"


@pytest.mark.parametrize("key", PYTHON_KEYS)
def test_plan_falls_back_per_profile_when_the_reply_is_unusable(key):
    plan = plan_project_full("A tiny inventory manager", lambda prompt, json_mode: "not json", get_profile(key))
    assert plan.source.startswith("fallback") and plan.package
    validate_plan({"package": plan.package, "tasks": [dataclasses.asdict(t) for t in plan.tasks]},
                  get_profile(key), plan.package)


def test_planner_prompt_describes_the_selected_project_type():
    seen = []
    plan_project("A budget tool", lambda prompt, json_mode: seen.append(prompt) or "x", get_profile("cli"))
    prompt = seen[0]
    assert "command-line tool" in prompt and "tests/" in prompt and "<package>" in prompt
    assert "{pkg}" not in prompt and "{description}" not in prompt and "FastAPI app" not in prompt


# ---- static checks -----------------------------------------------------------


def test_static_check_flags_missing_modules_syntax_errors_and_missing_tests(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/cli.py": "from app.ghost import thing\n", "app/__main__.py": "x = (\n"})
    issues = pychecks.static_check(tmp_path, "app", get_profile("cli"))
    text = " | ".join(i["description"] for i in issues)
    assert "imports module `app.ghost`" in text and "syntax error" in text and "no tests" in text
    hints = {i["missing_file"] for i in issues if "missing_file" in i}
    assert {"app/ghost.py", "tests/test_app.py"} <= hints


def test_static_check_resolves_relative_imports_and_reports_owners(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/a.py": "from .b import x\nfrom .gone import y\n", "app/b.py": "x = 1\n",
                      "app/cli.py": "", "app/__main__.py": "", "tests/test_a.py": "def test_a():\n    pass\n"})
    issues = pychecks.static_check(tmp_path, "app", get_profile("cli"), {"app/a.py": "frontend"})
    assert [i["missing_file"] for i in issues if "missing_file" in i] == ["app/gone.py"]
    assert issues[0]["owner"] == "backend"  # a missing module is created by a backend developer


def test_static_check_attributes_a_broken_file_to_the_role_that_owns_it(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/cli.py": "def (:\n", "app/__main__.py": "",
                      "tests/test_a.py": "def test_a():\n    pass\n"})
    issues = pychecks.static_check(tmp_path, "app", get_profile("cli"), {"app/cli.py": "frontend"})
    assert issues[0]["owner"] == "frontend" and issues[0]["file"] == "app/cli.py"


# ---- runtime checks ----------------------------------------------------------


def test_runtime_check_passes_for_a_healthy_cli(tmp_path):
    _write(tmp_path, {f: GOOD[f] for f in ("app/core.py", "app/cli.py", "tests/test_cli.py")})
    _write(tmp_path, {"app/__init__.py": "", "app/__main__.py": MAINS["cli"]})
    assert pychecks.check(tmp_path, "app", get_profile("cli")) == []
    assert not list(tmp_path.rglob("__pycache__")), "generated projects must not collect bytecode caches"


def test_entry_command_that_exits_non_zero_is_reported_with_its_output(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/cli.py": "", "tests/test_a.py": "def test_a():\n    pass\n",
                      "app/__main__.py": "import sys\nprint('bad config', file=sys.stderr)\nsys.exit(3)\n"})
    issues = pychecks.runtime_check(tmp_path, "app", get_profile("cli"))
    assert issues and "exited with code 3" in issues[0]["description"] and "bad config" in issues[0]["description"]


def test_failing_test_produces_a_code_issue_and_a_test_issue(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/cli.py": "", "app/__main__.py": MAINS["cli"].replace("main", "x"),
                      "app/core.py": "def add():\n    raise RuntimeError('boom')\n",
                      "tests/test_core.py": "from app.core import add\n\n\ndef test_add():\n    add()\n"})
    _write(tmp_path, {"app/__main__.py": "print('hi')\n"})
    owners = {"app/core.py": "backend", "tests/test_core.py": "qa"}
    issues = pychecks.runtime_check(tmp_path, "app", get_profile("cli"), owners)
    assert {(i["owner"], i["file"]) for i in issues} == {("backend", "app/core.py"), ("qa", "tests/test_core.py")}
    assert all("boom" in i["description"] for i in issues)


def test_data_project_that_writes_no_output_is_reported(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/__main__.py": "print('analysed')\n",
                      "data/sample.csv": "a\n1\n", "tests/test_a.py": "def test_a():\n    pass\n"})
    issues = pychecks.runtime_check(tmp_path, "app", get_profile("data"))
    assert any("wrote nothing into output/" in i["description"] for i in issues)


def test_game_is_driven_through_stdin_and_cannot_hang_waiting_for_input(tmp_path):
    _write(tmp_path, {"app/__init__.py": "", "app/game.py": GOOD["app/game.py"], "app/__main__.py": MAINS["game"],
                      "tests/test_game.py": GOOD["tests/test_game.py"]})
    assert pychecks.check(tmp_path, "app", get_profile("game")) == []
    hangs = dict(MAINS, game="input()\nwhile True:\n    pass\n")["game"]
    _write(tmp_path, {"app/__main__.py": hangs})
    monkey = pychecks.ENTRY_TIMEOUT
    pychecks.ENTRY_TIMEOUT = 3
    try:
        results = pychecks.run_demo(tmp_path, "app", get_profile("game"))
    finally:
        pychecks.ENTRY_TIMEOUT = monkey
    assert results and results[0]["ok"] is False


def test_api_server_error_on_a_route_is_reported(tmp_path):
    broken = GOOD["app/main.py"].replace("return ITEMS", "raise RuntimeError('db down')")
    _write(tmp_path, {"app/__init__.py": "", "app/store.py": GOOD["app/store.py"], "app/main.py": broken,
                      "tests/test_a.py": "def test_a():\n    pass\n"})
    issues = pychecks.runtime_check(tmp_path, "app", get_profile("api"), {"app/main.py": "backend"})
    assert any("GET /api/items returned HTTP 500" in i["description"] for i in issues)


# ---- end-to-end builds --------------------------------------------------------


def _build(tmp_path, key, llm=None, strategy="fixed", **cfg):
    return build_project(
        get_profile(key).example, out_dir=tmp_path / key, strategy=strategy,
        llm=llm or ProfileLLM(key), config=BuildConfig(**cfg), project_type=key,
    )


@pytest.mark.parametrize("key", PYTHON_KEYS)
def test_each_project_type_is_built_tested_and_validated(tmp_path, key):
    result = _build(tmp_path, key)
    root = result.root
    assert result.success, result.final_issues
    assert result.final_issues == [] and result.plan_source == "llm"
    assert all(t["status"] == "COMPLETED" for t in result.state["tasks"])
    assert any(p.name.startswith("test_") for p in (root / "tests").glob("*.py")), "QA wrote the tests"
    assert (root / "docs/architecture.md").is_file() and (root / "docs/qa-report.md").is_file()
    assert (root / "README.md").is_file() and (root / "requirements.txt").is_file()
    assert result.state["project_type"] == key and result.state["package"] == "app"
    assert not list(root.rglob("__pycache__")) and not (root / ".pytest_cache").exists()
    run = json.loads((root / "ekatra-run.json").read_text())
    assert run["config"]["project_type"] == key and run["config"]["package"] == "app"


def test_data_project_really_produces_its_output(tmp_path):
    result = _build(tmp_path, "data")
    assert json.loads((result.root / "output/summary.json").read_text()) == {"count": 8, "total": 36}


def test_readme_explains_how_to_run_each_type(tmp_path):
    assert "python -m app --help" in (_build(tmp_path, "cli").root / "README.md").read_text()
    assert "uvicorn app.main:app" in (_build(tmp_path, "api").root / "README.md").read_text()


def test_adaptive_strategy_works_for_a_python_profile(tmp_path):
    result = _build(tmp_path, "cli", strategy="adaptive")
    assert result.success and result.metrics.adaptive["adaptive_decision_count"] >= 1


def test_failing_tests_drive_a_repair_round_that_fixes_the_code(tmp_path):
    llm = ProfileLLM("cli", broken={"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"})
    result = _build(tmp_path, "cli", llm=llm, repair_rounds=2)
    descriptions = [t["description"] for t in result.state["tasks"]]
    assert any(d.startswith("Fix review findings") for d in descriptions)
    assert result.final_issues == [] and result.success
    assert "boom" not in (result.root / "app/core.py").read_text()
    assert any("FIX task" in p and "boom" in p for p in llm.calls), "the fixer was shown the test failure"


def test_without_repair_the_failing_test_is_reported_as_high(tmp_path):
    llm = ProfileLLM("cli", broken={"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"})
    result = _build(tmp_path, "cli", llm=llm, repair_rounds=0)
    assert not result.success
    assert any(i["severity"] == "high" and "boom" in i["description"] for i in result.final_issues)


def test_checks_can_be_switched_off_for_python_projects(tmp_path):
    llm = ProfileLLM("cli", broken={"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"})
    result = _build(tmp_path, "cli", llm=llm, repair_rounds=0, smoke_test=False)
    assert result.final_issues == []  # static analysis alone cannot see the runtime failure


def test_qa_reviewer_is_shown_the_check_evidence(tmp_path):
    llm = ProfileLLM("cli", broken={"app/core.py": "def add(items, text):\n    raise RuntimeError('boom')\n"})
    _build(tmp_path, "cli", llm=llm, repair_rounds=0)
    review = [p for p in llm.calls if "QA engineer reviewing this command-line tool" in p]
    assert review and "boom" in review[0]


def test_web_projects_are_unchanged_by_profiles(tmp_path):
    from tests.test_build import FakeLLM

    result = build_project("A tiny shop website", out_dir=tmp_path / "web", strategy="fixed", llm=FakeLLM(),
                           config=BuildConfig(smoke_test=False))
    assert result.success and result.state["project_type"] == "web"
    assert (result.root / "backend/main.py").is_file() and (result.root / "frontend/index.html").is_file()


# ---- blame when the failure is inside the test (the real todo_cli failure) ----------

SWALLOWING_CLI = (
    "import argparse\n\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(prog='todo')\n"
    "    try:\n        parser.parse_args(argv)\n    except SystemExit as exc:\n"
    "        return exc.code if isinstance(exc.code, int) else 2\n    return 0\n"
)
HELP_TEST = (
    "import pytest\nfrom todo_cli.cli import main\n\n\ndef test_cli_help(capsys):\n"
    "    with pytest.raises(SystemExit) as exc_info:\n        main(['--help'])\n    assert exc_info.value.code == 0\n"
)


def _todo_cli_project(tmp_path, test=HELP_TEST):
    _write(tmp_path, {
        "todo_cli/__init__.py": "", "todo_cli/core.py": "def add(items, text):\n    return items + [text]\n",
        "todo_cli/cli.py": SWALLOWING_CLI, "todo_cli/__main__.py": MAINS["cli"].replace("app", "todo_cli"),
        "tests/test_cli.py": test,
    })
    return {"todo_cli/core.py": "backend", "todo_cli/cli.py": "frontend", "tests/test_cli.py": "qa"}


def test_a_failure_inside_the_test_blames_the_module_it_imports_and_that_modules_owner(tmp_path):
    owners = _todo_cli_project(tmp_path)
    issues = pychecks.runtime_check(tmp_path, "todo_cli", get_profile("cli"), owners)
    assert {(i["owner"], i["file"]) for i in issues} == {("frontend", "todo_cli/cli.py"), ("qa", "tests/test_cli.py")}
    assert all("DID NOT RAISE" in i["description"] for i in issues)
    assert not any(i["file"] == "todo_cli/core.py" for i in issues), "the test never imports core.py"


def test_imported_modules_are_found_from_all_import_styles(tmp_path):
    _write(tmp_path, {"todo_cli/__init__.py": "", "todo_cli/a.py": "", "todo_cli/b.py": "", "todo_cli/c/__init__.py": "x = 1\n",
                      "tests/test_x.py": "import todo_cli.a\nfrom todo_cli.b import thing\nfrom todo_cli import c\nimport os\n"})
    assert pychecks._imported_modules(tmp_path, "tests/test_x.py", "todo_cli") == [
        "todo_cli/a.py", "todo_cli/b.py"]  # a package __init__ is not a blameable module
    assert pychecks._imported_modules(tmp_path, "tests/missing.py", "todo_cli") == []


def test_a_test_that_imports_nothing_blames_every_owned_module_not_just_backend_ones(tmp_path):
    owners = _todo_cli_project(tmp_path, test="def test_math():\n    assert 1 == 2\n")
    issues = pychecks.runtime_check(tmp_path, "todo_cli", get_profile("cli"), owners)
    assert {(i["owner"], i["file"]) for i in issues} == {
        ("backend", "todo_cli/core.py"), ("frontend", "todo_cli/cli.py"), ("qa", "tests/test_cli.py")}


def test_the_repair_round_fixes_a_frontend_owned_module_when_the_test_fails_inside_itself(tmp_path):
    broken = GOOD["app/cli.py"].replace("return 0", "return 1")  # main() reports failure; no exception in the code
    llm = ProfileLLM("cli", broken={"app/cli.py": broken})
    result = _build(tmp_path, "cli", llm=llm, repair_rounds=2)
    fixes = [t for t in result.state["tasks"] if t["description"].startswith("Fix review findings")]
    assert any(t["role"] == "frontend" for t in fixes), "the interface developer owns cli.py and must get a fix task"
    assert result.final_issues == [] and result.success
    assert "return 1" not in (result.root / "app/cli.py").read_text()
