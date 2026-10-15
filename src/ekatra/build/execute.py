"""Real task execution: one agent, one task, one Gemini call, real files.

Developers (architect/backend/frontend) are asked for a JSON list of files and
only the files the plan assigned to the task are written. QA and Security read
the project, are given the static-validation evidence, and write a report and a
structured issue list. Every read and write goes through ``Agent.use_tool`` so
role permissions (write prefixes) and path containment are enforced and every
call is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ekatra.agents.base import Agent, Role
from ekatra.build.plan import LLMFn, PlannedTask, extract_json
from ekatra.build.validate import Issue, validate_project
from ekatra.workspace import Workspace

_CONTEXT_FILE_LIMIT = 9000
_CONTEXT_TOTAL_LIMIT = 40000
_ARCH_LIMIT = 14000
_MAX_TOKENS = 32768

_STANDARDS = """Project standards (follow exactly):
- Backend: Python 3, FastAPI. backend/main.py defines `app`, includes routers from the other backend
  modules, and mounts the frontend/ directory with StaticFiles(directory=..., html=True) at "/" AFTER
  all /api routes (compute the path from Path(__file__).resolve().parent.parent / "frontend").
  Import siblings as `from backend.<module> import ...`. Only fastapi and the standard library.
- Frontend: static HTML, CSS and vanilla JavaScript (no build step, no external CDNs). Call the backend
  with fetch() using the exact /api paths from docs/architecture.md. The site must look polished and be
  responsive.
- Write COMPLETE, working files. No placeholders, no TODOs, no "rest of the code" comments."""


@dataclass
class TaskOutcome:
    ok: bool
    summary: str = ""
    issues: list[Issue] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    error: str = ""


def _read(agent: Agent, task_id: str, path: str) -> str:
    if agent.workspace is None or not agent.workspace.exists(path):
        return ""  # not written yet: not a tool failure
    try:
        result = agent.use_tool("read_file", task_id=task_id, path=path)
    except (PermissionError, KeyError):
        return ""
    return result.output["content"] if result.success and result.output else ""


def _strip_fence(content: str) -> str:
    text = content.strip("\n")
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            return "\n".join(lines[1:-1]) + "\n"
    return content if content.endswith("\n") else content + "\n"


def _project_files(workspace: Workspace) -> list[str]:
    return sorted(
        p for p in workspace.list_files(".") if not p.startswith("ekatra-") and p.split("/")[0] in {"backend", "frontend", "docs"}
    )


def _context(agent: Agent, task_id: str, paths: list[str]) -> str:
    chunks, total = [], 0
    for path in paths:
        text = _read(agent, task_id, path)
        if not text:
            continue
        text = text[:_CONTEXT_FILE_LIMIT]
        if total + len(text) > _CONTEXT_TOTAL_LIMIT:
            break
        total += len(text)
        chunks.append(f"--- {path} ---\n{text}")
    return "\n\n".join(chunks) if chunks else "(none yet)"


def _retry_note(previous_error: str) -> str:
    if not previous_error:
        return ""
    return (
        f"\nYour previous attempt FAILED: {previous_error}\n"
        "Fix that: return EVERY required file, each with complete non-empty content.\n"
    )


def _developer_prompt(role: str, planned: PlannedTask, description: str, arch: str,
                      files_ctx: str, listing: list[str], fix_issues: list[Issue],
                      previous_error: str = "") -> str:
    fixing = _retry_note(previous_error)
    if fix_issues:
        lines = "\n".join(f"- [{i['severity']}] {i['file']}: {i['description']}" for i in fix_issues)
        fixing += f"\nThis is a FIX task. Correct these problems by rewriting the files below:\n{lines}\n"
    return f"""You are the {role} developer on a software team building this website:

{description}

Your task: {planned.description}
{fixing}
You must write exactly these files (and no others): {', '.join(planned.deliverables)}

{_STANDARDS}

Architecture document (docs/architecture.md):
{arch or '(not written yet)'}

Files currently in the project: {', '.join(listing) or '(none)'}

Existing files relevant to you:
{files_ctx}

Return ONLY a JSON object: {{"files": [{{"path": "<one of your files>", "content": "<full file>"}}],
"summary": "<one sentence on what you built>"}}"""


def _architect_prompt(planned: PlannedTask, description: str, previous_error: str = "") -> str:
    return f"""You are the software architect for this website project:

{description}

Your task: {planned.description}
{_retry_note(previous_error)}
{_STANDARDS}

Write docs/architecture.md in Markdown with these sections, precise enough for developers working in
parallel who cannot talk to each other:
1. Overview and pages (every page and what it shows)
2. File layout: every file under backend/ and frontend/ with one line on its purpose and its public
   functions/classes (names and signatures)
3. REST API contract: every endpoint as `METHOD /api/path` with request JSON and response JSON examples
4. Data model: fields and types
5. How the frontend and backend connect (backend/main.py serves frontend/ at "/")

Return ONLY a JSON object: {{"files": [{{"path": "docs/architecture.md", "content": "<markdown>"}}],
"summary": "<one sentence>"}}"""


def _reviewer_prompt(role: str, planned: PlannedTask, description: str, files_ctx: str,
                     evidence: list[Issue], previous_error: str = "") -> str:
    focus = ("correctness: bugs, broken flows, mismatches between frontend calls and backend routes, "
             "missing validation") if role == "qa" else (
             "security: injection, XSS (unsafe innerHTML), missing input validation, unsafe file access, "
             "CORS, secrets in code, error leakage")
    ev = "\n".join(f"- [{i['severity']}] {i['file']}: {i['description']}" for i in evidence) or "(none)"
    return f"""You are the {role.upper()} engineer reviewing this website project:

{description}

Your task: {planned.description}
{_retry_note(previous_error)}Focus on {focus}.

Static analysis already found these problems (treat them as real):
{ev}

Project files:
{files_ctx}

Return ONLY a JSON object:
{{"report_markdown": "<a clear Markdown report>",
 "issues": [{{"severity": "high|medium|low", "owner": "backend|frontend", "file": "<path>",
              "description": "<specific problem and how to fix it>"}}],
 "summary": "<one sentence>"}}
Only list real, specific issues that exist in the files above; use an empty list if there are none."""


def execute_task(
    agent: Agent,
    task_id: str,
    planned: PlannedTask,
    *,
    workspace: Workspace,
    description: str,
    llm: LLMFn,
    fix_issues: list[Issue] | None = None,
    dependency_paths: list[str] | None = None,
    previous_error: str = "",
) -> TaskOutcome:
    """Run one planned task as ``agent`` and return a structured outcome."""
    role = planned.role
    try:
        if role == "architect":
            prompt = _architect_prompt(planned, description, previous_error)
        elif role in ("qa", "security"):
            evidence = validate_project(workspace.root) if role == "qa" else []
            paths = [p for p in _project_files(workspace) if not p.startswith("docs/") or p == "docs/architecture.md"]
            prompt = _reviewer_prompt(role, planned, description, _context(agent, task_id, paths), evidence, previous_error)
        else:
            arch = _read(agent, task_id, "docs/architecture.md")[:_ARCH_LIMIT]
            prompt = _developer_prompt(
                role, planned, description, arch,
                _context(agent, task_id, dependency_paths or []),
                _project_files(workspace), fix_issues or [], previous_error,
            )
        data = extract_json(llm(prompt, True))
        if not isinstance(data, dict):
            raise ValueError("model reply is not a JSON object")

        if role in ("qa", "security"):
            return _write_report(agent, task_id, planned, data, (evidence if role == "qa" else []))

        written: list[str] = []
        missing: list[str] = []
        by_path = {f.get("path"): f.get("content") for f in data.get("files") or [] if isinstance(f, dict)}
        for path in planned.deliverables:
            content = by_path.get(path)
            if not isinstance(content, str) or not content.strip():
                if path.endswith("__init__.py"):
                    content = "# package\n"  # an empty package marker is legitimate
                else:
                    missing.append(path)
                    continue
            result = agent.use_tool("write_file", task_id=task_id, path=path, content=_strip_fence(content))
            if not result.success:
                raise ValueError(f"write {path} failed: {result.error}")
            written.append(path)  # keep partial progress even if others are missing
        if missing:
            raise ValueError(f"model did not return non-empty content for: {', '.join(missing)}")
        return TaskOutcome(True, str(data.get("summary") or f"wrote {', '.join(written)}")[:300], files=written)
    except Exception as exc:  # noqa: BLE001 - reported as a failed attempt
        return TaskOutcome(False, error=f"{type(exc).__name__}: {str(exc)[:300]}")


def _write_report(agent: Agent, task_id: str, planned: PlannedTask, data: dict[str, Any],
                  evidence: list[Issue]) -> TaskOutcome:
    issues: list[Issue] = list(evidence)
    for raw in data.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        owner = raw.get("owner") if raw.get("owner") in ("backend", "frontend") else "backend"
        severity = raw.get("severity") if raw.get("severity") in ("high", "medium", "low") else "medium"
        issues.append({"severity": severity, "owner": owner, "file": str(raw.get("file", ""))[:120],
                       "description": str(raw.get("description", ""))[:400]})
    report = data.get("report_markdown")
    if not isinstance(report, str) or not report.strip():
        report = "# Report\n\n" + ("\n".join(f"- {i['file']}: {i['description']}" for i in issues) or "No issues found.")
    if evidence:
        report += "\n\n## Static analysis\n" + "\n".join(f"- [{i['severity']}] {i['file']}: {i['description']}" for i in evidence)
    path = planned.deliverables[0]
    result = agent.use_tool("write_file", task_id=task_id, path=path, content=_strip_fence(report))
    if not result.success:
        return TaskOutcome(False, error=f"write {path} failed: {result.error}")
    return TaskOutcome(True, str(data.get("summary") or f"{len(issues)} issue(s) reported")[:300],
                       issues=issues, files=[path])


__all__ = ["TaskOutcome", "execute_task"]
