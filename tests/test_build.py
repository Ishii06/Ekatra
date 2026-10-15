"""Tests for the real build mode, using a scripted fake LLM (no network)."""

import json
import re
import threading
import time

import pytest

from ekatra.build import BuildConfig, PlanError, build_project, plan_project, validate_plan, validate_project
from ekatra.build.__main__ import main as build_cli
from ekatra.build.plan import extract_json, fallback_plan
from ekatra.llm import gemini
from ekatra.llm.gemini import GeminiProviderError, generate

MAIN_PY = '''from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()


@app.get("/api/items")
def items():
    return []


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="site")
'''
BROKEN_MAIN_PY = MAIN_PY.replace("app.mount", "# app.mount").replace("StaticFiles", "Static")
INDEX_HTML = '<html><head><link href="style.css" rel="stylesheet"></head><body><script src="app.js"></script></body></html>\n'
APP_JS = "fetch('/api/items').then(r => r.json());\n"


def _task(key, role, deliverables, deps=(), **kw):
    return {"key": key, "role": role, "description": f"do {key}", "dependencies": list(deps),
            "deliverables": deliverables, "complexity": kw.get("complexity", 4), "priority": 2}


def wide_plan(backend_modules=5):
    tasks = [_task("architecture", "architect", ["docs/architecture.md"])]
    mods = []
    for i in range(backend_modules):
        tasks.append(_task(f"mod_{i}", "backend", [f"backend/mod_{i}.py"], ["architecture"]))
        mods.append(f"mod_{i}")
    tasks.append(_task("backend_main", "backend", ["backend/__init__.py", "backend/main.py"], ["architecture"] + mods))
    tasks.append(_task("frontend_page", "frontend", ["frontend/index.html", "frontend/style.css"], ["architecture"]))
    tasks.append(_task("frontend_app", "frontend", ["frontend/app.js"], ["architecture", "frontend_page"]))
    tasks.append(_task("qa", "qa", ["docs/qa-report.md"], ["backend_main", "frontend_app"]))
    tasks.append(_task("security", "security", ["docs/security-report.md"], ["backend_main", "frontend_app"]))
    return {"tasks": tasks}


class FakeLLM:
    """Answers each kind of prompt the build mode sends."""

    def __init__(self, plan=None, delay=0.0, broken_main_first=False, fail_once=(), qa_issue=False):
        self.plan = plan if plan is not None else wide_plan()
        self.delay = delay
        self.broken_main_first = broken_main_first
        self.fail_once = set(fail_once)
        self.qa_issue = qa_issue
        self.lock = threading.Lock()
        self.calls = []
        self.failed = set()

    def __call__(self, prompt, json_mode):
        with self.lock:
            self.calls.append(prompt)
        time.sleep(self.delay)
        if "Project Manager" in prompt:
            return json.dumps(self.plan) if self.plan != "garbage" else "not json at all"
        if "software architect" in prompt:
            return json.dumps({"files": [{"path": "docs/architecture.md", "content": "# Architecture\n"}], "summary": "designed"})
        if "reviewing this website project" in prompt:
            issues = []
            if self.qa_issue and "QA engineer" in prompt:
                issues = [{"severity": "low", "owner": "backend", "file": "backend/main.py", "description": "nit"}]
            return json.dumps({"report_markdown": "# Report\nok", "issues": issues, "summary": "reviewed"})
        wanted = re.search(r"exactly these files \(and no others\): (.*)", prompt).group(1).split(", ")
        key = wanted[0]
        with self.lock:
            if key in self.fail_once and key not in self.failed:
                self.failed.add(key)
                raise RuntimeError("simulated provider outage")
        files = []
        for path in wanted:
            if path == "backend/main.py":
                content = MAIN_PY if ("FIX task" in prompt or not self.broken_main_first) else BROKEN_MAIN_PY
            elif path == "frontend/index.html":
                content = INDEX_HTML
            elif path == "frontend/app.js":
                content = APP_JS
            elif path.endswith(".css"):
                content = "body { margin: 0; }\n"
            else:
                content = "X = 1\n"
            files.append({"path": path, "content": content})
        return json.dumps({"files": files, "summary": f"wrote {key}"})


def _build(tmp_path, llm, strategy="adaptive", **cfg):  # noqa: E302
    cfg.setdefault("smoke_test", False)  # runtime checks have their own tests
    return build_project("A tiny shop website", out_dir=tmp_path / "site", strategy=strategy,
                         llm=llm, config=BuildConfig(**cfg))


# ---- plan --------------------------------------------------------------------


def test_extract_json_handles_code_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_validate_plan_accepts_a_good_plan():
    tasks = validate_plan(wide_plan())
    assert tasks[0].key == "architecture" and len(tasks) == 11


@pytest.mark.parametrize("mutate,message", [
    (lambda p: p["tasks"][1].update(dependencies=["nope"]), "unknown"),
    (lambda p: p["tasks"][1].update(deliverables=["frontend/x.py"]), "may only write"),
    (lambda p: p["tasks"][1].update(deliverables=["backend/../../evil.py"]), "unsafe"),
    (lambda p: p["tasks"][2].update(deliverables=p["tasks"][1]["deliverables"]), "owned by both"),
    (lambda p: p["tasks"][1].update(role="designer"), "unsupported role"),
    (lambda p: p["tasks"][1].update(deliverables=[]), "at least one deliverable"),
])
def test_validate_plan_rejects_bad_plans(mutate, message):
    plan = wide_plan()
    mutate(plan)
    with pytest.raises(PlanError, match=message):
        validate_plan(plan)


def test_validate_plan_requires_entry_points_and_all_roles():
    plan = wide_plan()
    plan["tasks"] = [t for t in plan["tasks"] if t["role"] != "security"]
    with pytest.raises(PlanError, match="security"):
        validate_plan(plan)


def test_plan_falls_back_when_llm_reply_is_unusable():
    tasks, source = plan_project("a shop", FakeLLM(plan="garbage"))
    assert source.startswith("fallback") and [t.key for t in tasks] == [t.key for t in fallback_plan("a shop")]
    validate_plan({"tasks": [t.__dict__ for t in tasks]})  # the fallback is itself a valid plan


def test_plan_falls_back_when_provider_raises():
    def boom(prompt, json_mode):
        raise GeminiProviderError("no key")

    assert plan_project("x", boom)[1].startswith("fallback")


# ---- build -------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_build_produces_a_complete_validated_project(tmp_path, strategy):
    result = _build(tmp_path, FakeLLM(), strategy)
    root = result.root
    for path in ("backend/main.py", "frontend/index.html", "frontend/app.js", "docs/architecture.md",
                 "docs/qa-report.md", "docs/security-report.md", "README.md", "requirements.txt", "ekatra-run.json"):
        assert (root / path).is_file(), path
    assert result.success and result.final_issues == []
    assert all(t["status"] == "COMPLETED" for t in result.state["tasks"])
    run = json.loads((root / "ekatra-run.json").read_text())
    assert run["config"]["engine"] == "live" and run["config"]["model"]["name"]
    assert "api_key" not in json.dumps(run).lower()


def test_tool_calls_are_recorded_for_every_agent_action(tmp_path):
    result = _build(tmp_path, FakeLLM(), "fixed")
    assert result.metrics.tools["total_tool_calls"] >= 11
    assert result.metrics.tools["failed_calls"] == 0


def test_fixed_strategy_never_spawns(tmp_path):
    result = _build(tmp_path, FakeLLM(delay=0.02), "fixed")
    assert result.metrics.adaptive["spawn_events"] == 0
    assert len(result.state["agents"]) == 6


def test_adaptive_strategy_spawns_agents_that_do_real_work(tmp_path):
    result = _build(tmp_path, FakeLLM(delay=0.05), "adaptive")
    agents = result.metrics.agent["agents"]
    spawned = [a for a in agents if a["layout"] == "dynamic"]
    assert result.metrics.adaptive["spawn_events"] >= 1
    assert spawned and any(a["execution_count"] > 0 for a in spawned)
    assert result.success


def test_provider_failure_is_retried(tmp_path):
    result = _build(tmp_path, FakeLLM(fail_once={"backend/mod_0.py"}), "fixed")
    types = [e["type"] for e in result.state["observability_events"]]
    assert "task_failed" in types and "task_retried" in types
    assert result.success


def test_task_that_keeps_failing_cancels_dependents(tmp_path):
    class AlwaysFail(FakeLLM):
        def __call__(self, prompt, json_mode):
            if "backend/mod_0.py" in prompt and "exactly these files" in prompt:
                raise RuntimeError("down")
            return super().__call__(prompt, json_mode)

    result = _build(tmp_path, AlwaysFail(), "fixed", max_retries=1, repair_rounds=0)
    statuses = {t["status"] for t in result.state["tasks"]}
    assert "FAILED" in statuses and "CANCELLED" in statuses
    assert not result.success


def test_repair_round_fixes_issues_found_by_static_validation(tmp_path):
    result = _build(tmp_path, FakeLLM(broken_main_first=True), "fixed", repair_rounds=1)
    keys = [t["description"] for t in result.state["tasks"]]
    assert any(d.startswith("Fix review findings") for d in keys)
    assert result.final_issues == [] and "StaticFiles" in (result.root / "backend/main.py").read_text()


def test_without_repair_the_defect_is_reported(tmp_path):
    result = _build(tmp_path, FakeLLM(broken_main_first=True), "fixed", repair_rounds=0)
    assert any("StaticFiles" in i["description"] for i in result.final_issues)
    assert not result.success or all(i["severity"] != "high" for i in result.final_issues)


def test_quality_metrics_come_from_qa_and_validation(tmp_path):
    result = _build(tmp_path, FakeLLM(qa_issue=True), "fixed", repair_rounds=0)
    quality = result.metrics.quality
    assert quality["defects_detected"] == 1
    assert quality["test_pass_rate"] == 1.0
    assert quality["counts_by_category"]["final_validation"] == 1


def test_unknown_strategy_rejected(tmp_path):
    with pytest.raises(ValueError):
        _build(tmp_path, FakeLLM(), "hybrid")


# ---- validator ---------------------------------------------------------------


def _write(root, files):
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def test_validator_flags_missing_files_syntax_errors_and_contract_mismatch(tmp_path):
    _write(tmp_path, {
        "backend/main.py": MAIN_PY.replace('"/api/items"', '"/api/things"'),
        "backend/bad.py": "def (:\n",
        "frontend/index.html": '<script src="missing.js"></script>',
        "frontend/app.js": "fetch(`/api/items/${id}`)",
    })
    descriptions = " | ".join(i["description"] for i in validate_project(tmp_path))
    assert "syntax error" in descriptions
    assert "missing.js" in descriptions
    assert "/api/items/x" in descriptions


def test_validator_accepts_router_prefixes_and_path_params(tmp_path):
    _write(tmp_path, {
        "backend/main.py": MAIN_PY + "\nfrom backend.items import router\napp.include_router(router)\n",
        "backend/__init__.py": "",
        "backend/items.py": 'from fastapi import APIRouter\nrouter = APIRouter(prefix="/api/things")\n'
                            '@router.get("/{thing_id}")\ndef one(thing_id: int):\n    return {}\n',
        "frontend/index.html": '<script src="app.js"></script>',
        "frontend/app.js": "fetch(`/api/things/${id}`); fetch('/api/items');",
    })
    assert validate_project(tmp_path) == []


def test_validator_reports_missing_local_import(tmp_path):
    _write(tmp_path, {
        "backend/main.py": MAIN_PY + "\nfrom backend.ghost import thing\n",
        "frontend/index.html": "<html></html>",
    })
    assert any("ghost" in i["description"] for i in validate_project(tmp_path))


# ---- Gemini wrapper ----------------------------------------------------------


class _Response:
    def __init__(self, text):
        self.text = text


class _Client:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(gemini, "build_gemini_client", lambda settings: client)


def test_generate_retries_transient_errors_then_succeeds(monkeypatch):
    client = _Client([RuntimeError("503 UNAVAILABLE"), RuntimeError("429 RESOURCE_EXHAUSTED"), "hello"])
    _patch_client(monkeypatch, client)
    sleeps = []
    assert generate("hi", sleep=sleeps.append) == "hello"
    assert client.calls == 3 and len(sleeps) == 2


def test_generate_raises_immediately_on_non_transient_error_without_leaking_key(monkeypatch):
    from ekatra.config.settings import get_settings

    secret = "AIza-TOPSECRET-123"
    monkeypatch.setattr(get_settings(), "gemini_api_key", secret)
    client = _Client([RuntimeError(f"400 bad request key={secret}")])
    _patch_client(monkeypatch, client)
    with pytest.raises(GeminiProviderError) as info:
        generate("hi", sleep=lambda s: None)
    assert secret not in str(info.value) and client.calls == 1


def test_generate_gives_up_after_retries(monkeypatch):
    client = _Client([RuntimeError("503")] * 4)
    _patch_client(monkeypatch, client)
    with pytest.raises(GeminiProviderError):
        generate("hi", retries=3, sleep=lambda s: None)
    assert client.calls == 4


# ---- CLI ---------------------------------------------------------------------


def test_cli_requires_an_api_key(capsys):
    assert build_cli(["a shop"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


# ---- weaker-model behaviour --------------------------------------------------


def test_empty_init_file_is_accepted_and_partial_progress_is_kept(tmp_path):
    class Sloppy(FakeLLM):
        """Omits one deliverable on the first attempt and returns an empty __init__.py."""

        def __call__(self, prompt, json_mode):
            reply = super().__call__(prompt, json_mode)
            if "exactly these files (and no others): backend/__init__.py, backend/main.py" in prompt:
                data = json.loads(reply)
                for f in data["files"]:
                    if f["path"] == "backend/__init__.py":
                        f["content"] = ""
                if "previous attempt FAILED" not in prompt:
                    data["files"] = [f for f in data["files"] if f["path"] != "backend/main.py"]
                    self.saw_first = True
                return json.dumps(data)
            return reply

    llm = Sloppy()
    result = _build(tmp_path, llm, "fixed")
    assert result.success
    assert (result.root / "backend/__init__.py").is_file()
    retry_prompts = [p for p in llm.calls if "previous attempt FAILED" in p]
    assert retry_prompts and "backend/main.py" in retry_prompts[0]


# ---- repair can create missing files -----------------------------------------


class MissingModuleLLM(FakeLLM):
    """backend/main.py imports backend.models, which no planned task creates."""

    def __call__(self, prompt, json_mode):
        reply = super().__call__(prompt, json_mode)
        if "exactly these files (and no others)" in prompt and "backend/main.py" in prompt.split("\n\nYou must")[0] + prompt:
            data = json.loads(reply)
            for f in data["files"]:
                if f["path"] == "backend/main.py" and "backend.models" not in f["content"]:
                    f["content"] += "\nfrom backend.models import X\n"
            return json.dumps(data)
        return reply


def test_validator_names_the_file_that_would_fix_a_missing_import_or_asset(tmp_path):
    _write(tmp_path, {
        "backend/main.py": MAIN_PY + "\nfrom backend.models import X\n",
        "frontend/index.html": '<script src="app.js"></script><link href="css/site.css">',
    })
    hints = {i["missing_file"] for i in validate_project(tmp_path) if "missing_file" in i}
    assert hints == {"backend/models.py", "frontend/app.js", "frontend/css/site.css"}


def test_repair_round_creates_a_missing_module(tmp_path):
    result = _build(tmp_path, MissingModuleLLM(), "fixed", repair_rounds=1)
    assert (result.root / "backend/models.py").is_file()
    assert result.final_issues == [] and result.success


def test_without_repair_a_missing_module_is_reported_as_high(tmp_path):
    result = _build(tmp_path, MissingModuleLLM(), "fixed", repair_rounds=0)
    assert any(i["severity"] == "high" and i.get("missing_file") == "backend/models.py"
               for i in result.final_issues)
    assert not result.success


# ---- runtime smoke test --------------------------------------------------------

from ekatra.build.smoke import smoke_test  # noqa: E402


def test_smoke_test_passes_for_a_healthy_site(tmp_path):
    _write(tmp_path, {"backend/main.py": MAIN_PY, "backend/__init__.py": "",
                      "frontend/index.html": INDEX_HTML, "frontend/app.js": APP_JS})
    assert smoke_test(tmp_path) == []


def test_smoke_test_reports_a_crash_at_import_and_blames_the_file(tmp_path):
    _write(tmp_path, {"backend/main.py": MAIN_PY + "\nfrom backend import helper\n",
                      "backend/__init__.py": "",
                      "backend/helper.py": "import backend.does_not_exist\n",
                      "frontend/index.html": INDEX_HTML})
    issues = smoke_test(tmp_path)
    assert issues and issues[0]["severity"] == "high"
    assert "failed to import or start" in issues[0]["description"]
    assert issues[0]["file"].startswith("backend/")


def test_smoke_test_reports_a_server_error_on_an_api_route(tmp_path):
    broken = MAIN_PY.replace("return []", "raise RuntimeError('boom')")
    _write(tmp_path, {"backend/main.py": broken, "backend/__init__.py": "",
                      "frontend/index.html": INDEX_HTML, "frontend/app.js": APP_JS})
    assert any("GET /api/items returned HTTP 500" in i["description"] for i in smoke_test(tmp_path))


def test_smoke_test_does_not_pass_secrets_to_generated_code(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-secret")
    probe = MAIN_PY + "\nimport os\nLEAK = os.environ.get('GEMINI_API_KEY')\nassert LEAK is None, 'secret leaked'\n"
    _write(tmp_path, {"backend/main.py": probe, "backend/__init__.py": "",
                      "frontend/index.html": INDEX_HTML})
    assert smoke_test(tmp_path) == []


def test_smoke_failure_triggers_repair_and_can_be_disabled(tmp_path):
    class RuntimeBroken(FakeLLM):
        def __call__(self, prompt, json_mode):
            reply = super().__call__(prompt, json_mode)
            if "backend/main.py" in prompt and "FIX task" not in prompt and "exactly these files" in prompt:
                data = json.loads(reply)
                for f in data["files"]:
                    if f["path"] == "backend/main.py":
                        f["content"] = f["content"].replace("return []", "raise RuntimeError('boom')")
                return json.dumps(data)
            return reply

    repaired = _build(tmp_path, RuntimeBroken(), "fixed", repair_rounds=1, smoke_test=True)
    assert repaired.final_issues == [] and repaired.success

    unchecked = build_project("A tiny shop website", out_dir=tmp_path / "nosmoke", strategy="fixed",
                              llm=RuntimeBroken(), config=BuildConfig(repair_rounds=0, smoke_test=False))
    assert unchecked.final_issues == []  # static analysis alone cannot see the runtime error
