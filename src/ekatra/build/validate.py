"""Static validation of a generated website project.

These checks are the QA agent's evidence. They never *run* generated code: Python
is parsed with ``ast``, HTML/JS are scanned with regular expressions, and if a
``node`` binary is available JavaScript is syntax-checked with ``node --check``
(which parses without executing).

Each issue is a JSON-safe dict:
``{"severity", "owner", "file", "description"}`` where ``owner`` is the role that
should fix it (``backend`` or ``frontend``).
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

Issue = dict[str, Any]

_API_CALL = re.compile(r"""["'`](/api/[A-Za-z0-9_\-./{}$:]*)""")
_ROUTE = re.compile(r"""@\w+\.(?:get|post|put|patch|delete)\(\s*["']([^"']*)["']""")
_PREFIX = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*["']([^"']*)["']""")
_MOUNT_PREFIX = re.compile(r"""include_router\([^)]*prefix\s*=\s*["']([^"']*)["']""")
_ASSET = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""")


def _issue(severity: str, owner: str, file: str, description: str, missing_file: str = "") -> Issue:
    """``missing_file`` names a file whose creation would resolve the issue."""
    issue: Issue = {"severity": severity, "owner": owner, "file": file, "description": description}
    if missing_file:
        issue["missing_file"] = missing_file
    return issue


def _normalize_call(path: str) -> str:
    path = re.sub(r"\$\{[^}]*\}", "x", path)
    path = re.sub(r"\{[^}]*\}", "x", path)
    return path.split("?")[0].rstrip("/") or "/"


def _route_matches(call: str, route: str) -> bool:
    pattern = re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(route.rstrip("/") or "/"))
    return re.fullmatch(pattern, call) is not None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def validate_project(root: Path) -> list[Issue]:
    """Return the static issues found in the project under ``root``."""
    issues: list[Issue] = []
    backend, frontend = root / "backend", root / "frontend"

    # -- backend ------------------------------------------------------------
    main = backend / "main.py"
    if not main.is_file():
        issues.append(_issue("high", "backend", "backend/main.py", "backend/main.py is missing"))
    else:
        text = _read(main)
        if "FastAPI(" not in text or not re.search(r"^app\s*=", text, re.M):
            issues.append(_issue("high", "backend", "backend/main.py",
                                 "backend/main.py must define `app = FastAPI(...)`"))
        if "StaticFiles" not in text:
            issues.append(_issue("medium", "backend", "backend/main.py",
                                 "backend/main.py does not serve the frontend/ folder (StaticFiles)"))
    py_files = sorted(backend.rglob("*.py")) if backend.is_dir() else []
    for py in py_files:
        rel = py.relative_to(root).as_posix()
        try:
            tree = ast.parse(_read(py))
        except SyntaxError as exc:
            issues.append(_issue("high", "backend", rel, f"syntax error line {exc.lineno}: {exc.msg}"))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = None
            if node.level >= 1 and node.module:
                target = backend / (node.module.replace(".", "/"))
            elif node.module and node.module.startswith("backend."):
                target = root / node.module.replace(".", "/")
            if target is not None and not (target.with_suffix(".py").is_file() or target.is_dir()):
                issues.append(_issue("high", "backend", rel,
                                     f"imports module `{node.module}` which does not exist",
                                     target.relative_to(root).with_suffix(".py").as_posix()))

    # -- frontend -----------------------------------------------------------
    index = frontend / "index.html"
    if not index.is_file():
        issues.append(_issue("high", "frontend", "frontend/index.html", "frontend/index.html is missing"))
    else:
        for ref in _ASSET.findall(_read(index)):
            if re.match(r"^(https?:|//|#|data:|mailto:)", ref) or ref.startswith("/api"):
                continue
            target = frontend / ref.lstrip("/").split("?")[0].split("#")[0]
            if not target.exists():
                missing = target.relative_to(root).as_posix() if target.suffix in {".js", ".css", ".html"} else ""
                issues.append(_issue("medium", "frontend", "frontend/index.html",
                                     f"references `{ref}` which does not exist in frontend/", missing))
    node = shutil.which("node")
    for js in sorted(frontend.rglob("*.js")) if frontend.is_dir() else []:
        if not node:
            break
        try:
            done = subprocess.run([node, "--check", str(js)], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode != 0:
            message = (done.stderr.strip().splitlines() or ["syntax error"])[-1][:200]
            issues.append(_issue("high", "frontend", js.relative_to(root).as_posix(), f"JavaScript: {message}"))

    # -- API contract: every /api call in the frontend has a backend route ----
    calls: dict[str, str] = {}
    for f in sorted(frontend.rglob("*")) if frontend.is_dir() else []:
        if f.suffix in {".js", ".html"}:
            for call in _API_CALL.findall(_read(f)):
                calls.setdefault(_normalize_call(call), f.relative_to(root).as_posix())
    routes: list[str] = []
    prefixes = {""}
    for py in py_files:
        text = _read(py)
        routes += _ROUTE.findall(text)
        prefixes.update(_PREFIX.findall(text))
        prefixes.update(_MOUNT_PREFIX.findall(text))
    for call, source in calls.items():
        if not any(_route_matches(call, p.rstrip("/") + "/" + r.lstrip("/") if r else p or "/")
                   for p in prefixes for r in routes):
            issues.append(_issue("high", "backend", source,
                                 f"frontend calls `{call}` but no matching backend route was found"))
    return issues


__all__ = ["Issue", "validate_project"]
