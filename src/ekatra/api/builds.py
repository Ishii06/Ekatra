"""REST + SSE endpoints for real (Gemini-driven) builds.

``POST /api/builds`` starts a build in a background thread. The scheduler
publishes a consistent state snapshot after every change; clients read it with
``GET /api/builds/{id}`` or follow it live over ``GET /api/builds/{id}/stream``
(Server-Sent Events). Generated files are listed and read through the build's
:class:`~ekatra.workspace.Workspace`, so paths can never leave the project folder.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ekatra.api.summary import workload_and_risk
from ekatra.build import pychecks
from ekatra.build.execute import is_visible
from ekatra.build.live import LIVE_WORKLOAD, BuildConfig, build_project
from ekatra.build.profiles import PROFILES, get_profile
from ekatra.build.plan import LLMFn
from ekatra.build.smoke import scrubbed_env
from ekatra.config.settings import get_settings
from ekatra.observability.metrics import compute_metrics
from ekatra.workspace import PathTraversalError, Workspace

router = APIRouter()

PROJECTS_DIR = Path(__file__).resolve().parents[3] / "projects"
BUILDS: dict[str, dict[str, Any]] = {}
SMOKE_TEST = True  # run the generated app during the build; tests switch it off
_LOCK = threading.Lock()

_AREAS = {"backend", "frontend", "docs", "tests", "data"}
_MAX_FILE_BYTES = 300_000
_LOG_TAIL = 400


class BuildCreateRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=600)
    strategy: str = Field("adaptive", pattern="^(fixed|adaptive)$")
    repair_rounds: int = Field(2, ge=0, le=3)
    project_type: str = Field("web", pattern="^(" + "|".join(PROFILES) + ")$")


def _make_llm() -> LLMFn | None:
    """The LLM used by builds; ``None`` means Gemini. Overridden in tests."""
    return None


def _empty_state() -> dict[str, Any]:
    return {"tasks": [], "agents": [], "observability_events": [], "adaptive_decisions": [],
            "communication": [], "tool_calls": [], "plan_source": "", "final_issues": []}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:28] or "site"


def _run_build(build_id: str) -> None:
    entry = BUILDS[build_id]

    def progress(message: str) -> None:
        entry["log"].append(message)
        entry["version"] += 1

    def on_update(state: dict[str, Any]) -> None:
        entry["state"] = state
        entry["version"] += 1

    try:
        result = build_project(
            entry["description"],
            out_dir=entry["out_dir"],
            strategy=entry["strategy"],
            llm=_make_llm(),
            config=BuildConfig(repair_rounds=entry["repair_rounds"], smoke_test=SMOKE_TEST),
            progress=progress,
            on_update=on_update,
            project_type=entry["project_type"],
        )
        entry["state"] = result.state
        entry["success"] = result.success
        entry["status"] = "completed"
    except Exception as exc:  # noqa: BLE001 - surfaced to the client
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        entry["status"] = "failed"
    finally:
        entry["finished_at"] = time.time()
        entry["version"] += 1


def _list_files(out_dir: Path) -> list[dict[str, Any]]:
    workspace = Workspace(out_dir)
    files = []
    for rel in workspace.list_files("."):
        if not is_visible(rel):
            continue
        top = rel.split("/")[0]
        info = workspace.metadata(rel)
        files.append({
            "path": rel,
            "bytes": info["size_bytes"],
            "area": top if top in _AREAS else ("project" if "/" not in rel else "source"),
            "modified_at": datetime.fromtimestamp(
                workspace.resolve(rel).stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return sorted(files, key=lambda f: f["modified_at"])


def _payload(entry: dict[str, Any]) -> dict[str, Any]:
    state = entry["state"]
    workload, risk = workload_and_risk(state, LIVE_WORKLOAD)
    metrics = compute_metrics(state).to_dict()
    end = entry.get("finished_at") or time.time()
    profile = get_profile(entry["project_type"])
    return {
        "project_type": profile.key,
        "project_label": profile.label,
        "runnable": profile.runnable,
        "has_tests": profile.kind == "python",
        "package": state.get("package", ""),
        "run_id": entry["build_id"],
        "scenario_id": "live_build",
        "strategy": entry["strategy"],
        "status": entry["status"],
        "success": entry.get("success"),
        "description": entry["description"],
        "plan_source": state.get("plan_source", ""),
        "agents": state.get("agents", []),
        "tasks": state.get("tasks", []),
        "adaptive_decisions": state.get("adaptive_decisions", []),
        "workload": workload,
        "risk": risk,
        "communication": [],
        "tool_summary": metrics.get("tools", {}),
        "observability_events": state.get("observability_events", []),
        "metrics": metrics,
        "project_state": "PLANNING" if not state.get("tasks") else (
            "COMPLETED" if entry["status"] == "completed" else "EXECUTING"),
        "error": entry.get("error"),
        "version": entry["version"],
        "elapsed_seconds": round(end - entry["started_at"], 1),
        "files": _list_files(entry["out_dir"]) if Path(entry["out_dir"]).exists() else [],
        "log": entry["log"][-_LOG_TAIL:],
        "final_issues": state.get("final_issues", []),
        "out_dir": str(entry["out_dir"]),
    }


def _get(build_id: str) -> dict[str, Any]:
    entry = BUILDS.get(build_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Build {build_id!r} not found")
    return entry


@router.post("/builds")
def start_build(req: BuildCreateRequest) -> dict[str, Any]:
    if _make_llm() is None and not get_settings().has_api_key():
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured on the server")
    with _LOCK:
        if any(b["status"] == "running" for b in BUILDS.values()):
            raise HTTPException(status_code=409, detail="A build is already running")
        build_id = f"build-{uuid.uuid4().hex[:10]}"
        BUILDS[build_id] = {
            "build_id": build_id, "description": req.description.strip(), "strategy": req.strategy,
            "repair_rounds": req.repair_rounds, "status": "running", "state": _empty_state(),
            "log": [], "project_type": req.project_type,
            "version": 0, "started_at": time.time(), "finished_at": None, "error": None,
            "out_dir": PROJECTS_DIR / f"{_slug(req.description)}-{req.strategy}-{build_id[-6:]}",
        }
        threading.Thread(target=_run_build, args=(build_id,), daemon=True).start()
    return {"run_id": build_id, "scenario_id": "live_build", "strategy": req.strategy, "status": "running"}


@router.get("/builds")
def list_builds() -> list[dict[str, Any]]:  # noqa: D103
    return [
        {"run_id": b["build_id"], "description": b["description"], "strategy": b["strategy"],
         "status": b["status"], "started_at": b["started_at"]}
        for b in sorted(BUILDS.values(), key=lambda b: b["started_at"], reverse=True)
    ]


@router.get("/builds/{build_id}")
def get_build(build_id: str) -> dict[str, Any]:
    return _payload(_get(build_id))


@router.get("/builds/{build_id}/stream")
async def stream_build(build_id: str) -> StreamingResponse:
    _get(build_id)

    async def events():
        last = -1
        while True:
            entry = BUILDS.get(build_id)
            if entry is None:
                yield "event: error\ndata: {}\n\n"
                return
            if entry["version"] != last:
                last = entry["version"]
                yield f"data: {json.dumps(_payload(entry), default=str)}\n\n"
            if entry["status"] != "running":
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/builds/{build_id}/files")
def list_build_files(build_id: str) -> list[dict[str, Any]]:
    entry = _get(build_id)
    return _list_files(entry["out_dir"]) if Path(entry["out_dir"]).exists() else []


@router.get("/builds/{build_id}/files/{path:path}")
def read_build_file(build_id: str, path: str) -> dict[str, Any]:
    entry = _get(build_id)
    if not is_visible(path):
        raise HTTPException(status_code=404, detail="File not found")
    workspace = Workspace(entry["out_dir"])
    try:
        if not workspace.is_file(path):
            raise HTTPException(status_code=404, detail="File not found")
        raw = workspace.resolve(path).read_bytes()
    except PathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid path") from None
    truncated = len(raw) > _MAX_FILE_BYTES
    return {
        "path": workspace.relative(path).as_posix(),
        "content": raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace"),
        "bytes": len(raw),
        "truncated": truncated,
    }


# -- running a generated site -------------------------------------------------
#
# Launching executes the generated backend, so it only ever happens when a client
# explicitly asks, on 127.0.0.1, with API keys stripped from the environment.

SITES: dict[str, subprocess.Popen] = {}
SITE_URLS: dict[str, str] = {}
_MAX_SITES = 3


def _site_env() -> dict[str, str]:
    return scrubbed_env()  # no API keys, and the site must not import Ekatra


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _site_running(build_id: str) -> bool:
    proc = SITES.get(build_id)
    return proc is not None and proc.poll() is None


def _stop_site(build_id: str) -> None:
    proc = SITES.pop(build_id, None)
    SITE_URLS.pop(build_id, None)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@atexit.register
def _stop_all_sites() -> None:
    for build_id in list(SITES):
        _stop_site(build_id)


def _site_status(build_id: str) -> dict[str, Any]:
    running = _site_running(build_id)
    url = SITE_URLS.get(build_id) if running else None
    entry = BUILDS.get(build_id)
    api = bool(entry) and entry["project_type"] == "api"
    return {"running": running, "url": url, "docs_url": url + "docs" if url and api else None}


@router.get("/builds/{build_id}/launch")
def site_status(build_id: str) -> dict[str, Any]:
    _get(build_id)
    return _site_status(build_id)


@router.post("/builds/{build_id}/launch")
def launch_site(build_id: str) -> dict[str, Any]:
    entry = _get(build_id)
    if entry["status"] == "running":
        raise HTTPException(status_code=409, detail="The build is still running")
    out_dir = Path(entry["out_dir"])
    profile = get_profile(entry["project_type"])
    if not profile.runnable:
        raise HTTPException(status_code=400, detail=f"A {profile.noun} has no server to start; use Run tests or Run demo")
    package = entry["state"].get("package") or ""
    module = "backend.main" if profile.key == "web" else f"{package}.main"
    if not (out_dir / (module.replace(".", "/") + ".py")).is_file():
        raise HTTPException(status_code=400, detail=f"The build has no {module.replace('.', '/')}.py to run")
    if _site_running(build_id):
        return _site_status(build_id)
    if sum(1 for b in SITES if _site_running(b)) >= _MAX_SITES:
        raise HTTPException(status_code=409, detail="Too many sites are running; stop one first")

    port = _free_port()
    log_path = out_dir / "ekatra-site.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", f"{module}:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=out_dir, env=_site_env(), stdout=log, stderr=subprocess.STDOUT,
        )
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            urllib.request.urlopen(url, timeout=1).close()
            up = True
        except urllib.error.HTTPError:
            up = True  # the server answered (an API service has no homepage)
        except Exception:  # noqa: BLE001 - not ready yet
            up = False
        if up:
            SITES[build_id], SITE_URLS[build_id] = proc, url
            return _site_status(build_id)
        time.sleep(0.3)
    if proc.poll() is None:
        proc.kill()
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-600:].strip()
    raise HTTPException(status_code=500, detail=f"The site did not start: {tail or 'no output'}")


@router.delete("/builds/{build_id}/launch")
def stop_site(build_id: str) -> dict[str, Any]:
    _get(build_id)
    _stop_site(build_id)
    return _site_status(build_id)


# -- project types, tests and demos -------------------------------------------


@router.get("/build-profiles")
def list_profiles() -> list[dict[str, Any]]:
    return [p.public() for p in PROFILES.values()]


def _finished_python_build(build_id: str):
    entry = _get(build_id)
    if entry["status"] == "running":
        raise HTTPException(status_code=409, detail="The build is still running")
    profile = get_profile(entry["project_type"])
    if profile.kind != "python":
        raise HTTPException(status_code=400, detail="Only Python project types have tests and a demo")
    return entry, profile


@router.post("/builds/{build_id}/tests")
def run_build_tests(build_id: str) -> dict[str, Any]:
    entry, _ = _finished_python_build(build_id)
    root = Path(entry["out_dir"])
    if not (root / "tests").is_dir():
        raise HTTPException(status_code=400, detail="The build has no tests/ folder")
    return pychecks.run_tests(root)


@router.post("/builds/{build_id}/demo")
def run_build_demo(build_id: str) -> dict[str, Any]:
    entry, profile = _finished_python_build(build_id)
    results = pychecks.run_demo(Path(entry["out_dir"]), entry["state"].get("package") or "", profile)
    if not results:
        raise HTTPException(status_code=400, detail=f"A {profile.noun} has no demo command; use Run tests")
    return {"ok": all(r["ok"] for r in results), "results": results}


__all__ = ["BUILDS", "PROJECTS_DIR", "SITES", "router"]
