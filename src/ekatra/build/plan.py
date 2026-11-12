"""LLM-driven project planning for real builds.

The Project Manager asks Gemini to decompose a project description into tasks for the
selected project profile (website, API, command-line tool, ...). The reply is *data*,
never control flow: it is parsed and strictly validated (roles, dependencies, file
ownership, size limits) before any task is created, and a deterministic fallback plan
is used when the reply is unusable. The adaptive controller is unaffected - it only
ever sees the validated tasks.
"""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from typing import Any, Callable

from ekatra.build.profiles import PYTHON_RESERVED, WEB, Profile
from ekatra.build.types import PlannedTask

# llm(prompt, json_mode) -> text. Injected so tests never touch the network.
LLMFn = Callable[[str, bool], str]

MAX_TASKS = 16
# Where each role may write in the web profile (kept for compatibility).
ROLE_PREFIX = {
    "architect": "docs/",
    "backend": "backend/",
    "frontend": "frontend/",
    "qa": "docs/",
    "security": "docs/",
}
PLAN_PROMPT = WEB.plan_prompt
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_PACKAGE = re.compile(r"^[a-z][a-z0-9_]{1,24}$")
_STOPWORDS = {"a", "an", "the", "of", "for", "and", "to", "in", "with", "python", "simple", "small", "command",
              "line", "tool", "cli", "script", "library", "app", "application", "that", "which", "my"}


class PlanError(ValueError):
    """Raised when an LLM plan fails validation."""


@dataclass
class Plan:
    tasks: list[PlannedTask]
    source: str          # "llm" or "fallback: <why>"
    package: str = ""    # python profiles: the package directory name


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


def valid_package(name: Any) -> bool:
    return (isinstance(name, str) and bool(_PACKAGE.match(name)) and name not in PYTHON_RESERVED
            and not keyword.iskeyword(name))


def resolve_package(raw: Any, profile: Profile) -> str:
    """The package directory for python profiles (empty for the web profile)."""
    if profile.kind != "python":
        return ""
    name = raw.get("package") if isinstance(raw, dict) else None
    if valid_package(name):
        return name
    items = raw.get("tasks") if isinstance(raw, dict) else raw
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        for path in item.get("deliverables") or []:
            top = str(path).split("/")[0]
            if item.get("role") in ("backend", "frontend") and valid_package(top):
                return top
    return "app"


def fallback_package(description: str) -> str:
    words = [w for w in re.findall(r"[a-z]+", description.lower()) if w not in _STOPWORDS and len(w) > 1]
    name = "_".join(words[:2])[:24]
    return name if valid_package(name) else "app"


def validate_plan(raw: Any, profile: Profile = WEB, package: str | None = None, *,
                  strict: bool = True) -> list[PlannedTask]:
    """Validate a parsed LLM plan for ``profile`` and return normalized tasks.

    ``strict=False`` is used for change requests: the per-task rules (roles, write
    locations, dependencies, file ownership) still apply, but the plan need not contain
    every role, the entry files or the tests - those already exist in the project.
    """
    items = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise PlanError("plan must contain a non-empty 'tasks' list")
    if len(items) > MAX_TASKS:
        raise PlanError(f"plan has {len(items)} tasks; the limit is {MAX_TASKS}")
    pkg = package if package is not None else resolve_package(raw, profile)

    tasks: list[PlannedTask] = []
    seen: set[str] = set()
    owned: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise PlanError("each task must be an object")
        key, role = str(item.get("key", "")).strip(), str(item.get("role", "")).strip()
        if not _KEY.match(key) or key in seen:
            raise PlanError(f"invalid or duplicate task key {key!r}")
        if role not in profile.allowed_roles:
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
        prefixes = profile.prefixes_for(role, pkg)
        for path in deliverables:
            if not path.startswith(prefixes):
                raise PlanError(f"{role} task {key!r} may only write under {', '.join(prefixes)}: {path}")
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

    if not strict:
        return tasks
    roles = {t.role for t in tasks}
    for needed in profile.required_roles:
        if needed not in roles:
            raise PlanError(f"plan has no {needed} task")
    required = profile.required(pkg)
    if any(path not in owned for path in required):
        raise PlanError(f"plan must deliver {' and '.join(required)}")
    if profile.kind == "python":
        qa_owned = {t.key for t in tasks if t.role == "qa"}
        if not any(p.startswith("tests/test_") and p.endswith(".py") and k in qa_owned for p, k in owned.items()):
            raise PlanError("plan must include QA tests as tests/test_*.py files")
    return tasks


def fallback_plan(description: str, profile: Profile = WEB, package: str = "") -> list[PlannedTask]:
    """A small deterministic plan used when the LLM plan is unusable."""
    return profile.fallback(description, package)


def render_plan_prompt(profile: Profile, description: str) -> str:
    return profile.plan_prompt.replace("{pkg}", "<package>").format(description=description)


def plan_project_full(description: str, llm: LLMFn, profile: Profile = WEB) -> Plan:
    """Ask the LLM for a plan; fall back to the deterministic plan on failure."""
    reason = "no attempt"
    prompt = render_plan_prompt(profile, description)
    for _ in range(2):
        try:
            raw = extract_json(llm(prompt, True))
            pkg = resolve_package(raw, profile)
            return Plan(validate_plan(raw, profile, pkg), "llm", pkg)
        except (PlanError, json.JSONDecodeError) as exc:
            reason = str(exc)[:200]
        except Exception as exc:  # noqa: BLE001 - provider failure
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
            break
    pkg = fallback_package(description) if profile.kind == "python" else ""
    return Plan(fallback_plan(description, profile, pkg), f"fallback: {reason}", pkg)


def plan_project(description: str, llm: LLMFn, profile: Profile = WEB) -> tuple[list[PlannedTask], str]:
    """``(tasks, source)`` where source is ``"llm"`` or ``"fallback: <why>"``."""
    plan = plan_project_full(description, llm, profile)
    return plan.tasks, plan.source


__all__ = [
    "LLMFn", "MAX_TASKS", "PLAN_PROMPT", "Plan", "PlanError", "PlannedTask", "ROLE_PREFIX",
    "extract_json", "fallback_package", "fallback_plan", "plan_project", "plan_project_full",
    "render_plan_prompt", "resolve_package", "valid_package", "validate_plan",
]
