"""Change requests: modify a project that was already built.

A change is planned and executed with the same machinery as a build, but on the
existing project folder. The Project Manager reads the file list and the architecture
document and plans the smallest set of tasks that makes the change (validated like any
plan: roles, write locations, dependencies, one owner per file). Developers rewrite only
the files they were assigned, QA updates the tests, then the project's checks and the
repair loop run, so a change cannot silently break what already worked.

With no request text, the run only re-checks the project and repairs what the checks
find ("fix remaining issues").
"""

from __future__ import annotations

import json
from pathlib import Path

from ekatra.build.execute import is_visible
from ekatra.build.live import BuildConfig, BuildResult, Progress, Update, _LiveBuild, run_and_save, wrap_llm
from ekatra.build.plan import LLMFn, PlanError, extract_json, validate_plan
from ekatra.build.profiles import Profile, get_profile
from ekatra.build.types import PlannedTask
from ekatra.workspace import Workspace

MAX_REQUEST_CHARS = 600
MAX_LISTED_FILES = 80

CHANGE_PROMPT = """You are the Project Manager of a software team. The team already built this <<NOUN>>:

<<DESCRIPTION>>

Existing files (path, bytes):
<<FILES>>

Architecture document (docs/architecture.md):
<<ARCHITECTURE>>

The user now asks for this CHANGE:
<<REQUEST>>

Plan the smallest set of tasks that makes the change. Return ONLY a JSON object:
{"tasks": [{"key": "snake_case_id", "role": "architect|backend|frontend|qa|security",
  "description": "exactly what must change in these files", "priority": 1-3, "complexity": 1-5,
  "risk": 0-100, "dependencies": ["keys of EARLIER tasks"], "deliverables": ["every file this task writes"]}]}

Rules:
- Each task REWRITES existing files completely or creates new files. List every file it writes as a
  deliverable, with its full path. Say precisely what must change in `description`.
- Only touch files that must change. Use at most 6 tasks. Every file belongs to exactly one task.
- Where each role may write: <<LOCATIONS>>
- If behaviour changes, also update or add tests (the qa role, under tests/) so they match the new behaviour.
- If an endpoint, command, data field or file layout changes, an architect task first updates
  docs/architecture.md and the other tasks depend on it.
- If the request is impossible or too unclear, return {"tasks": [], "reason": "<why>"}.
"""


def plan_change(request: str, llm: LLMFn, profile: Profile, package: str, description: str,
                files: list[tuple[str, int]], architecture: str) -> list[PlannedTask]:
    """Ask the Project Manager for the tasks that implement ``request``."""
    locations = "; ".join(f"{role}: {', '.join(profile.prefixes_for(role, package))}"
                          for role in profile.allowed_roles)
    prompt = (CHANGE_PROMPT.replace("<<NOUN>>", profile.noun)
              .replace("<<DESCRIPTION>>", description or "(no description saved)")
              .replace("<<FILES>>", "\n".join(f"- {p} ({n})" for p, n in files[:MAX_LISTED_FILES]) or "(none)")
              .replace("<<ARCHITECTURE>>", architecture[:9000] or "(not available)")
              .replace("<<REQUEST>>", request)
              .replace("<<LOCATIONS>>", locations))
    reason = "no attempt"
    for _ in range(2):
        try:
            raw = extract_json(llm(prompt, True))
            if isinstance(raw, dict) and raw.get("tasks") == [] and raw.get("reason"):
                raise PlanError(f"The Project Manager could not plan this change: {str(raw['reason'])[:300]}")
            return validate_plan(raw, profile, package, strict=False)
        except PlanError as exc:
            if str(exc).startswith("The Project Manager could not plan"):
                raise
            reason = str(exc)[:240]
        except json.JSONDecodeError as exc:
            reason = f"the reply was not valid JSON ({exc.msg})"
    raise PlanError(f"Could not plan the change: {reason}")


def infer_owners(files: list[str], profile: Profile, package: str) -> dict[str, str]:
    """File -> role for a project whose plan was not saved (older builds)."""
    owners: dict[str, str] = {}
    for path in files:
        if path == "docs/architecture.md":
            owners[path] = "architect"
        elif path.startswith("docs/") and "security" in path:
            owners[path] = "security"
        elif path.startswith("docs/"):
            owners[path] = "qa"
        else:
            for role in ("backend", "frontend", "qa"):
                if path.startswith(profile.prefixes_for(role, package)) and role in profile.allowed_roles:
                    owners[path] = role
                    break
    return owners


def change_project(
    out_dir: str | Path,
    request: str | None,
    *,
    project_type: str,
    package: str = "",
    description: str = "",
    strategy: str = "adaptive",
    llm: LLMFn | None = None,
    config: BuildConfig | None = None,
    progress: Progress | None = None,
    on_update: Update | None = None,
    owners: dict[str, str] | None = None,
) -> BuildResult:
    """Apply ``request`` to the project in ``out_dir`` (or only re-check and repair if empty)."""
    request = (request or "").strip()
    if len(request) > MAX_REQUEST_CHARS:
        raise ValueError(f"the change request is longer than {MAX_REQUEST_CHARS} characters")
    profile = get_profile(project_type)
    cfg = config or BuildConfig()
    log = progress or (lambda message: None)
    llm = wrap_llm(llm, cfg)
    workspace = Workspace(out_dir)
    paths = [p for p in workspace.list_files(".") if is_visible(p)]
    if not paths:
        raise ValueError("there is nothing to change: the project folder has no files")
    number = 1 + len(list(Path(workspace.root).glob("ekatra-change-*.json")))

    plan: list[PlannedTask] = []
    if request:
        log(f"Planning the change with the Project Manager: {request}")
        sizes = [(p, workspace.resolve(p).stat().st_size) for p in paths]
        architecture = workspace.read_text("docs/architecture.md") if workspace.exists("docs/architecture.md") else ""
        plan = plan_change(request, llm, profile, package, description, sizes, architecture)
        log(f"Change plan: {len(plan)} task(s)")
        for pt in plan:
            log(f"  - {pt.key} [{pt.role}] -> {', '.join(pt.deliverables)}")
        source = "change"
    else:
        log("No new request: re-running the checks and repairing what they find")
        source = "repair"

    label = description or request or "Existing project"
    build = _LiveBuild(label, strategy, workspace, llm, cfg, log, on_update, profile, package)
    build.known_owners = {**infer_owners(paths, profile, package), **(owners or {})}
    build.change_request = request
    build.plan_source = source
    build.create_tasks(plan)
    return run_and_save(build, cfg=cfg, description=label, plan_source=source,
                        run_file=f"ekatra-change-{number}.json",
                        extra={"change_request": request, "change_number": number})


__all__ = ["MAX_REQUEST_CHARS", "change_project", "infer_owners", "plan_change"]
