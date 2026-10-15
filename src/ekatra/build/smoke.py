"""Runtime smoke check of a generated site.

Static analysis cannot see circular imports, wrong constructor calls or crashing
startup code, so the build also *runs* the generated app once: in a separate
Python process (working directory = the project, API keys removed from the
environment, hard timeout) it imports ``backend.main``, starts the app with
FastAPI's test client, requests ``/`` and every simple ``/api`` path the frontend
calls, and reports failures as issues the repair round can fix.

This executes generated code. It can be switched off with
``BuildConfig(smoke_test=False)`` / ``--no-smoke-test``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ekatra.build.validate import Issue

TIMEOUT_SECONDS = 30
_SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")

_SCRIPT = r'''
import json, pathlib, re, traceback
out = {"errors": []}
try:
    from fastapi.testclient import TestClient
    import backend.main as m
    with TestClient(m.app, raise_server_exceptions=False) as client:
        response = client.get("/")
        if response.status_code != 200:
            out["errors"].append(f"GET / returned HTTP {response.status_code}")
        paths = set()
        for f in pathlib.Path("frontend").rglob("*"):
            if f.suffix in (".js", ".html"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                paths |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]*)["'`]""", text))
        for path in sorted(paths)[:12]:
            response = client.get(path)
            if response.status_code >= 500:
                out["errors"].append(f"GET {path} returned HTTP {response.status_code}")
except BaseException:
    out["errors"].append("the app failed to import or start:\n" + traceback.format_exc()[-900:])
print("EKATRA_SMOKE " + json.dumps(out))
'''


def scrubbed_env() -> dict[str, str]:
    """The current environment without secrets or Ekatra's own import path."""
    env = {k: v for k, v in os.environ.items() if not any(w in k.upper() for w in _SECRET_WORDS)}
    env.pop("PYTHONPATH", None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _blame(error: str, root: Path) -> str:
    """The generated file that the last traceback frame points at."""
    frames = re.findall(r'File "([^"]+)", line \d+', error)
    for frame in reversed(frames):
        try:
            rel = Path(frame).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        if rel.startswith(("backend/", "frontend/")):
            return rel
    return "backend/main.py"


def smoke_test(root: Path) -> list[Issue]:
    """Run the generated app once and return what went wrong (empty = healthy)."""
    if not (root / "backend" / "main.py").is_file():
        return []
    try:
        done = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            cwd=root, env=scrubbed_env(), capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return [{"severity": "high", "owner": "backend", "file": "backend/main.py",
                 "description": f"the app did not finish starting within {TIMEOUT_SECONDS}s"}]
    line = next((ln for ln in done.stdout.splitlines() if ln.startswith("EKATRA_SMOKE ")), None)
    if line is None:
        tail = (done.stderr or done.stdout).strip()[-500:] or "no output"
        return [{"severity": "high", "owner": "backend", "file": "backend/main.py",
                 "description": f"the smoke test crashed: {tail}"}]
    issues: list[Issue] = []
    for error in json.loads(line[len("EKATRA_SMOKE "):])["errors"]:
        issues.append({"severity": "high", "owner": "backend", "file": _blame(error, root),
                       "description": error[:700]})
    return issues


__all__ = ["scrubbed_env", "smoke_test"]
