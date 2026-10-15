"""LLM-driven project planning for real builds.

The Project Manager asks Gemini to decompose a website description into tasks.
The reply is *data*, never control flow: it is parsed and strictly validated
(roles, dependencies, file ownership, size limits) before any task is created,
and a deterministic fallback plan is used when the reply is unusable. The
adaptive controller is unaffected - it only ever sees the validated tasks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ekatra.agents.base import Role

# llm(prompt, json_mode) -> text. Injected so tests never touch the network.
LLMFn = Callable[[str, bool], str]

MAX_TASKS = 16
# Where each role may write (matches tools.registry.WRITE_PREFIXES).
ROLE_PREFIX = {
    "architect": "docs/",
    "backend": "backend/",
    "frontend": "frontend/",
    "qa": "docs/",
    "security": "docs/",
}
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class PlanError(ValueError):
    """Raised when an LLM plan fails validation."""


@dataclass
class PlannedTask:
    key: str
    role: str
    description: str
    priority: int = 2
    complexity: int = 3
    risk: int = 20
    dependencies: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)


def extract_json(text: str) -> Any:
    """Parse a JSON document from a model reply (tolerates code fences)."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned, strict=False)  # allow raw newlines inside strings
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1], strict=False)
        raise


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _safe_path(path: Any) -> str:
    if not isinstance(path, str):
        raise PlanError(f"deliverable path must be a string, got {path!r}")
    cleaned = path.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/") or ":" in cleaned:
        raise PlanError(f"unsafe deliverable path {path!r}")
    return cleaned


def validate_plan(raw: Any) -> list[PlannedTask]:
    """Validate a parsed LLM plan and return normalized tasks."""
    items = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise PlanError("plan must contain a non-empty 'tasks' list")
    if len(items) > MAX_TASKS:
        raise PlanError(f"plan has {len(items)} tasks; the limit is {MAX_TASKS}")

    tasks: list[PlannedTask] = []
    seen: set[str] = set()
    owned: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise PlanError("each task must be an object")
        key, role = str(item.get("key", "")).strip(), str(item.get("role", "")).strip()
        if not _KEY.match(key) or key in seen:
            raise PlanError(f"invalid or duplicate task key {key!r}")
        if role not in ROLE_PREFIX:
            raise PlanError(f"task {key!r} has unsupported role {role!r}")
        description = str(item.get("description", "")).strip()
        if not description:
            raise PlanError(f"task {key!r} has no description")
        deps = [str(d) for d in item.get("dependencies") or []]
        unknown = [d for d in deps if d not in seen]
        if unknown:
            raise PlanError(f"task {key!r} depends on unknown/later tasks {unknown}")
        deliverables = [_safe_path(p) for p in item.get("deliverables") or []]
        if not deliverables:
            raise PlanError(f"task {key!r} must declare at least one deliverable")
        for path in deliverables:
            if not path.startswith(ROLE_PREFIX[role]):
                raise PlanError(f"{role} task {key!r} may only write under {ROLE_PREFIX[role]}: {path}")
            if path in owned:
                raise PlanError(f"{path} is owned by both {owned[path]!r} and {key!r}")
            owned[path] = key
        seen.add(key)
        tasks.append(
            PlannedTask(
                key=key,
                role=role,
                description=description,
                priority=_clamp(item.get("priority"), 1, 3, 2),
                complexity=_clamp(item.get("complexity"), 1, 5, 3),
                risk=_clamp(item.get("risk"), 0, 100, 20),
                dependencies=deps,
                deliverables=deliverables,
            )
        )

    roles = {t.role for t in tasks}
    for needed in ("architect", "backend", "frontend", "qa", "security"):
        if needed not in roles:
            raise PlanError(f"plan has no {needed} task")
    if "backend/main.py" not in owned or "frontend/index.html" not in owned:
        raise PlanError("plan must deliver backend/main.py and frontend/index.html")
    return tasks


def fallback_plan(description: str) -> list[PlannedTask]:
    """A small deterministic plan used when the LLM plan is unusable."""
    return [
        PlannedTask("architecture", "architect",
                    f"Design the architecture, REST API contract and data model for: {description}",
                    3, 3, 10, [], ["docs/architecture.md"]),
        PlannedTask("backend_core", "backend",
                    "Implement the data layer and business logic as described in docs/architecture.md.",
                    3, 4, 25, ["architecture"], ["backend/__init__.py", "backend/store.py"]),
        PlannedTask("backend_api", "backend",
                    "Implement backend/main.py: the FastAPI app, the /api routes from the contract, "
                    "and serve the frontend/ folder as static files at '/'.",
                    3, 3, 30, ["architecture", "backend_core"], ["backend/main.py"]),
        PlannedTask("frontend_page", "frontend",
                    "Implement frontend/index.html and frontend/style.css for the site.",
                    2, 3, 15, ["architecture"], ["frontend/index.html", "frontend/style.css"]),
        PlannedTask("frontend_app", "frontend",
                    "Implement frontend/app.js: calls the /api routes from the contract and renders data.",
                    2, 3, 20, ["architecture", "frontend_page"], ["frontend/app.js"]),
        PlannedTask("qa", "qa", "Review the whole project for defects and contract mismatches.",
                    3, 2, 20, ["backend_api", "frontend_app"], ["docs/qa-report.md"]),
        PlannedTask("security", "security", "Review the project for security weaknesses.",
                    3, 2, 40, ["backend_api", "frontend_app"], ["docs/security-report.md"]),
    ]


PLAN_PROMPT = """You are the Project Manager of a software team building a small, complete, \
working website from this description:

{description}

Decompose the work into between 8 and 14 tasks. Return ONLY a JSON object:
{{"tasks": [{{"key": "snake_case_id", "role": "architect|backend|frontend|qa|security",
  "description": "what to do, specific", "priority": 1-3, "complexity": 1-5, "risk": 0-100,
  "dependencies": ["keys of EARLIER tasks"], "deliverables": ["files this task writes"]}}]}}

Rules:
- Exactly one architect task first, key "architecture", deliverable "docs/architecture.md". It defines
  the page list, REST API contract (paths under /api, JSON shapes), data model and file layout.
- Backend files live under backend/, frontend files under frontend/ (static HTML/CSS/vanilla JS, no
  build step). QA and security tasks write one report each under docs/.
- The backend is a FastAPI app. backend/main.py defines `app`, mounts the frontend/ folder as static
  files at "/" AFTER the /api routes, and includes the other backend modules. Include
  backend/__init__.py. Data lives in memory or a local SQLite file; use only the standard library plus
  fastapi/uvicorn.
- Split work so several developers can work in parallel: several independent backend modules and
  several independent frontend pages/scripts. Integration files (backend/main.py,
  frontend/index.html) must depend on the other tasks of their role.
- Every file has exactly one owning task (no two tasks list the same deliverable).
- QA and security tasks depend on all developer tasks.
- Use real, concrete features for the description; no placeholders.
"""


def plan_project(description: str, llm: LLMFn) -> tuple[list[PlannedTask], str]:
    """Ask the LLM for a plan; fall back to the deterministic plan on failure.

    Returns ``(tasks, source)`` where source is ``"llm"`` or ``"fallback: <why>"``.
    """
    reason = "no attempt"
    for _ in range(2):
        try:
            reply = llm(PLAN_PROMPT.format(description=description), True)
            return validate_plan(extract_json(reply)), "llm"
        except (PlanError, json.JSONDecodeError) as exc:
            reason = str(exc)[:200]
        except Exception as exc:  # noqa: BLE001 - provider failure
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
            break
    return fallback_plan(description), f"fallback: {reason}"


__all__ = [
    "LLMFn", "MAX_TASKS", "PlanError", "PlannedTask", "ROLE_PREFIX",
    "extract_json", "fallback_plan", "plan_project", "validate_plan",
]
