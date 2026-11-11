"""Project profiles: what kind of software a build produces.

A profile is the only place that knows what a project type looks like: its file
layout, which role may write where, the standards given to agents, the plan rules,
the fallback plan, how the result is run and which checks apply. The six agent
roles, the task manager, the adaptive controller and the metrics are identical for
every profile.

Python profiles put source code in a package ``<pkg>/`` (chosen by the planner),
tests in ``tests/`` and documents in ``docs/``. The Backend developer owns core
logic, the Frontend developer owns the user-facing layer (command line, terminal
loop, report rendering) when there is one, and QA writes the pytest tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ekatra.build.types import PlannedTask

PYTHON_RESERVED = {"tests", "test", "docs", "data", "output", "ekatra"}


def _t(key, role, description, deps, files, priority=2, complexity=3, risk=20):
    return PlannedTask(key, role, description, priority, complexity, risk, list(deps), list(files))


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    noun: str                       # "website", "command-line tool", ...
    summary: str
    example: str
    kind: str                       # "web" or "python"
    allowed_roles: tuple[str, ...]
    required_roles: tuple[str, ...]
    required_files: tuple[str, ...]  # templates; "{pkg}" is replaced by the package name
    prefixes: dict[str, tuple[str, ...]]
    fixable_roles: tuple[str, ...]
    plan_prompt: str                 # uses {description}; "{pkg}" rendered by the planner
    standards: str
    architect_body: str
    qa_focus: str
    security_focus: str
    run_text: str                    # README "Run it" body
    requirements: str
    fallback: Callable[[str, str], list[PlannedTask]]
    runnable: str = ""               # "web" / "api": can be served from the dashboard
    role_titles: dict[str, str] = field(default_factory=dict)
    fix_defaults: dict[str, str] = field(default_factory=dict)

    def prefixes_for(self, role: str, pkg: str) -> tuple[str, ...]:
        return tuple(p.replace("{pkg}", pkg) for p in self.prefixes.get(role, ()))

    def required(self, pkg: str) -> tuple[str, ...]:
        return tuple(f.replace("{pkg}", pkg) for f in self.required_files)

    def render(self, text: str, pkg: str) -> str:
        return text.replace("{pkg}", pkg)

    def title_for(self, role: str) -> str:
        return self.role_titles.get(role, f"{role} developer")

    def fix_default(self, role: str, pkg: str) -> str:
        return self.render(self.fix_defaults.get(role, ""), pkg)

    def public(self) -> dict[str, object]:
        return {"key": self.key, "label": self.label, "summary": self.summary,
                "example": self.example, "runnable": self.runnable}


# ---------------------------------------------------------------------------------
# web (the original profile; wording kept identical)
# ---------------------------------------------------------------------------------

WEB_STANDARDS = """Project standards (follow exactly):
- Backend: Python 3, FastAPI. backend/main.py defines `app`, includes routers from the other backend
  modules, and mounts the frontend/ directory with StaticFiles(directory=..., html=True) at "/" AFTER
  all /api routes (compute the path from Path(__file__).resolve().parent.parent / "frontend").
  Import siblings as `from backend.<module> import ...`. Only fastapi and the standard library.
- Frontend: static HTML, CSS and vanilla JavaScript (no build step, no external CDNs). Call the backend
  with fetch() using the exact /api paths from docs/architecture.md. The site must look polished and be
  responsive.
- Write COMPLETE, working files. No placeholders, no TODOs, no "rest of the code" comments."""

WEB_PLAN_PROMPT = """You are the Project Manager of a software team building a small, complete, \
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

WEB_ARCHITECT = """Write docs/architecture.md in Markdown with these sections, precise enough for developers working in
parallel who cannot talk to each other:
1. Overview and pages (every page and what it shows)
2. File layout: every file under backend/ and frontend/ with one line on its purpose and its public
   functions/classes (names and signatures)
3. REST API contract: every endpoint as `METHOD /api/path` with request JSON and response JSON examples
4. Data model: fields and types
5. How the frontend and backend connect (backend/main.py serves frontend/ at "/")"""


def _web_fallback(description: str, pkg: str = "") -> list[PlannedTask]:
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


WEB = Profile(
    key="web", label="Web app", noun="website",
    summary="FastAPI backend serving a static HTML, CSS and JavaScript frontend.",
    example=("A personal finance tracker website where users can add income and expense transactions "
             "with categories, view a monthly summary with totals per category, and see a simple bar "
             "chart of spending by category."),
    kind="web",
    allowed_roles=("architect", "backend", "frontend", "qa", "security"),
    required_roles=("architect", "backend", "frontend", "qa", "security"),
    required_files=("backend/main.py", "frontend/index.html"),
    prefixes={"architect": ("docs/",), "backend": ("backend/",), "frontend": ("frontend/",),
              "qa": ("docs/",), "security": ("docs/",)},
    fixable_roles=("backend", "frontend"),
    plan_prompt=WEB_PLAN_PROMPT, standards=WEB_STANDARDS, architect_body=WEB_ARCHITECT,
    qa_focus=("correctness: bugs, broken flows, mismatches between frontend calls and backend routes, "
              "missing validation"),
    security_focus=("security: injection, XSS (unsafe innerHTML), missing input validation, unsafe file "
                    "access, CORS, secrets in code, error leakage"),
    run_text=("python -m venv .venv\n.venv\\Scripts\\activate        # Windows "
              "(use `source .venv/bin/activate` elsewhere)\npip install -r requirements.txt\n"
              "uvicorn backend.main:app --reload\n\nThen open http://127.0.0.1:8000"),
    requirements="fastapi\nuvicorn[standard]\n",
    fallback=_web_fallback, runnable="web",
    fix_defaults={"backend": "backend/main.py", "frontend": "frontend/index.html"},
)


# ---------------------------------------------------------------------------------
# python profiles
# ---------------------------------------------------------------------------------

_PY_STANDARDS = """Project standards (follow exactly):
- Python 3.11+, standard library only{extra}. pytest is used for tests. No network access, no external
  services, no API keys.
- All source code lives in the package `{pkg}/` at the project root; modules import each other as
  `from {pkg}.<module> import ...`. Tests live in `tests/` and import from the package; they are run
  from the project root with `python -m pytest`.
- Tests must be deterministic and self-contained: no network, no dependence on the current time, use
  pytest's tmp_path for any files, never write outside the project.
- {contract}
- Write COMPLETE, working files. No placeholders, no TODOs, no "rest of the code" comments."""

_PY_PLAN_PROMPT = """You are the Project Manager of a software team building a small, complete, \
working {noun} from this description:

{description}

Decompose the work into between 7 and 13 tasks. Return ONLY a JSON object:
{{"package": "short_snake_case_package_name",
  "tasks": [{{"key": "snake_case_id", "role": "architect|backend|frontend|qa|security",
  "description": "what to do, specific", "priority": 1-3, "complexity": 1-5, "risk": 0-100,
  "dependencies": ["keys of EARLIER tasks"], "deliverables": ["files this task writes"]}}]}}

Rules:
- Choose a short snake_case Python package name for the project (for example "todo_cli"). ALL source
  code lives in that package at the project root, written as `<package>/module.py`; tests live in
  `tests/`; documents in `docs/`.
- Exactly one architect task first, key "architecture", deliverable "docs/architecture.md". It defines
  the modules, every public function/class with its signature, the data formats and the behaviour
  contract.
- backend developers write the core logic modules under `<package>/` (include `<package>/__init__.py`).
{frontend_rule}
- QA writes the automated tests: one or more qa tasks whose deliverables are `tests/test_*.py` files
  (pytest), and one final qa task that writes `docs/qa-report.md`. Test tasks depend on the code they
  test.
- One security task writes `docs/security-report.md`.
- {contract}
- Split work so several developers can work in parallel: several independent modules, each owned by one
  task. Every file has exactly one owning task (no two tasks list the same deliverable). Reports depend
  on all developer and test tasks.
- Use real, concrete features for the description; no placeholders.
"""

_PY_ARCHITECT = """Write docs/architecture.md in Markdown with these sections, precise enough for developers working in
parallel who cannot talk to each other:
1. Overview: what the {noun} does, with concrete examples of how it is used (commands, calls, inputs
   and the exact outputs)
2. File layout: every file under {pkg}/, tests/ and data/ with one line on its purpose and its public
   functions/classes (names and exact signatures)
3. Data formats and storage
4. Behaviour contract: {contract}
5. Error handling and input validation rules"""

_PY_QA_FOCUS = ("correctness: logic bugs, unhandled edge cases, missing validation, behaviour that does not "
                "match the architecture document, and whether the tests really cover the features")
_PY_SECURITY_FOCUS = ("security: unsafe file or path handling (path traversal), command or SQL injection, unsafe "
                      "deserialisation, secrets in code, unvalidated input, error leakage")

_PY_FRONTEND_RULE = (
    "- frontend developers write the user-facing layer under `<package>/` (command-line parsing, terminal "
    "loop, report rendering); omit frontend tasks if the project has no such layer."
)

_PY_TITLES = {"backend": "backend developer", "frontend": "interface developer", "qa": "QA engineer"}


def _py_fallback_factory(spec: dict) -> Callable[[str, str], list[PlannedTask]]:
    """Build a fallback plan from a compact spec (see the profile definitions below)."""

    def build(description: str, pkg: str) -> list[PlannedTask]:
        p = pkg
        tasks = [_t("architecture", "architect",
                    f"Design the architecture for: {description}. Define modules, public signatures, data "
                    "formats and the behaviour contract.", [], ["docs/architecture.md"], 3, 3, 10)]
        code_keys = []
        for key, role, desc, files in spec["code"]:
            files = [f.replace("{pkg}", p) for f in files]
            deps = ["architecture"] + ([code_keys[0]] if code_keys and role != "backend" else [])
            tasks.append(_t(key, role, desc, deps, files, 3 if role == "backend" else 2,
                            4 if role == "backend" else 3, 25))
            code_keys.append(key)
        tasks.append(_t("tests", "qa", spec["tests"], list(code_keys),
                        [f.replace("{pkg}", p) for f in spec["test_files"]], 3, 3, 20))
        tasks.append(_t("qa_report", "qa", "Review the project for defects and write the QA report.",
                        code_keys + ["tests"], ["docs/qa-report.md"], 3, 2, 20))
        tasks.append(_t("security", "security", "Review the project for security weaknesses.",
                        code_keys + ["tests"], ["docs/security-report.md"], 3, 2, 40))
        return tasks

    return build


def _py_profile(*, key, label, noun, summary, example, contract, extra="", frontend=True,
                spec, required, runnable="", run_text, requirements="pytest\n", fix_defaults=None) -> Profile:
    roles = ("architect", "backend", "frontend", "qa", "security") if frontend else \
            ("architect", "backend", "qa", "security")
    standards = _PY_STANDARDS.replace("{extra}", extra).replace("{contract}", contract)
    plan_prompt = (_PY_PLAN_PROMPT.replace("{noun}", noun)
                   .replace("{frontend_rule}", _PY_FRONTEND_RULE if frontend else
                            "- there is no frontend role in this project; do not create frontend tasks.")
                   .replace("{contract}", contract))
    return Profile(
        key=key, label=label, noun=noun, summary=summary, example=example, kind="python",
        allowed_roles=roles, required_roles=("architect", "backend", "qa", "security"),
        required_files=tuple(required),
        prefixes={"architect": ("docs/",), "backend": ("{pkg}/", "data/"), "frontend": ("{pkg}/",),
                  "qa": ("tests/", "docs/"), "security": ("docs/",)},
        fixable_roles=("backend", "frontend", "qa") if frontend else ("backend", "qa"),
        plan_prompt=plan_prompt, standards=standards,
        architect_body=_PY_ARCHITECT.replace("{noun}", noun).replace("{contract}", contract),
        qa_focus=_PY_QA_FOCUS, security_focus=_PY_SECURITY_FOCUS,
        run_text=run_text, requirements=requirements, fallback=_py_fallback_factory(spec),
        runnable=runnable, role_titles=_PY_TITLES,
        fix_defaults=fix_defaults or {"backend": "{pkg}/__init__.py", "frontend": "{pkg}/__main__.py",
                                      "qa": "tests/test_{pkg}.py"},
    )


API = _py_profile(
    key="api", label="REST API service", noun="REST API service",
    summary="A FastAPI service with documented routes, tested with pytest and the test client.",
    example=("A library inventory REST API with endpoints to add, list, search and remove books, track "
             "which books are checked out, and report overdue loans. Validate all input and return clear "
             "error responses."),
    contract=("`{pkg}/main.py` defines `app = FastAPI(...)` with all routes under /api; use fastapi and the "
              "standard library only. Tests use `fastapi.testclient.TestClient` (httpx is installed). "
              "There is no frontend."),
    extra=", plus fastapi", frontend=False, runnable="api",
    spec={"code": [
        ("core", "backend", "Implement the data models, validation and in-memory or SQLite storage.",
         ["{pkg}/__init__.py", "{pkg}/store.py"]),
        ("routes", "backend", "Implement {pkg}/main.py: the FastAPI app and every /api route in the contract.",
         ["{pkg}/main.py"]),
    ], "tests": "Write pytest tests that call every route with the test client, including error cases.",
        "test_files": ["tests/test_api.py"]},
    required=("{pkg}/main.py",),
    run_text=("python -m venv .venv\n.venv\\Scripts\\activate        # Windows "
              "(use `source .venv/bin/activate` elsewhere)\npip install -r requirements.txt\n"
              "uvicorn {pkg}.main:app --reload\n\nThen open http://127.0.0.1:8000/docs"),
    requirements="fastapi\nuvicorn[standard]\nhttpx\npytest\n",
    fix_defaults={"backend": "{pkg}/main.py", "qa": "tests/test_api.py"},
)

CLI = _py_profile(
    key="cli", label="Command-line tool", noun="command-line tool",
    summary="An argparse tool with subcommands, run with `python -m <package>`.",
    example=("A command-line to-do manager. Users run commands like `add \"Buy milk\" --due 2026-12-01 "
             "--priority high`, `list --status pending`, `done <id>`, `delete <id>` and `stats`. Tasks are "
             "saved in a local JSON file. `stats` prints total, completed and overdue counts. Include input "
             "validation and clear error messages."),
    contract=("`{pkg}/cli.py` defines `main(argv=None) -> int` using argparse subcommands; `{pkg}/__main__.py` "
              "does `from {pkg}.cli import main` then `raise SystemExit(main())`. `python -m {pkg} --help` "
              "must work and exit 0. State is kept in a file whose path can be set with an option or "
              "environment variable."),
    spec={"code": [
        ("core", "backend", "Implement the core task logic, validation and file persistence.",
         ["{pkg}/__init__.py", "{pkg}/core.py"]),
        ("cli", "frontend", "Implement {pkg}/cli.py (argparse subcommands) and {pkg}/__main__.py.",
         ["{pkg}/cli.py", "{pkg}/__main__.py"]),
    ], "tests": "Write pytest tests that run main([...]) for every subcommand, including invalid input.",
        "test_files": ["tests/test_cli.py"]},
    required=("{pkg}/cli.py", "{pkg}/__main__.py"),
    run_text="python -m {pkg} --help",
    fix_defaults={"backend": "{pkg}/core.py", "frontend": "{pkg}/cli.py", "qa": "tests/test_cli.py"},
)

LIBRARY = _py_profile(
    key="library", label="Python library", noun="Python library",
    summary="An importable package with a documented public API and tests.",
    example=("A text utilities library with functions to slugify text, truncate by words, count word "
             "frequencies, detect the language of short text by common words, and wrap text to a width. "
             "Include type hints, docstrings and edge-case handling."),
    contract=("`{pkg}/__init__.py` re-exports the public API; `import {pkg}` must work with no side effects. "
              "Every public function has type hints and a docstring."),
    frontend=False,
    spec={"code": [
        ("core", "backend", "Implement the main public functions and their edge-case handling.",
         ["{pkg}/__init__.py", "{pkg}/core.py"]),
        ("helpers", "backend", "Implement the supporting helper functions.", ["{pkg}/helpers.py"]),
    ], "tests": "Write pytest tests covering every public function and its edge cases.",
        "test_files": ["tests/test_core.py"]},
    required=("{pkg}/__init__.py",),
    run_text="pip install -r requirements.txt\npython -c \"import {pkg}; print({pkg}.__doc__)\"\npython -m pytest",
    fix_defaults={"backend": "{pkg}/core.py", "qa": "tests/test_core.py"},
)

DATA = _py_profile(
    key="data", label="Data analysis script", noun="data analysis script",
    summary="Reads a bundled CSV, cleans it and writes a summary report.",
    example=("A sales data analysis script that reads a sales CSV (date, region, product, units, price), "
             "cleans bad rows, then reports total revenue per region and product, the best month, and "
             "writes the results to a summary file."),
    contract=("`python -m {pkg}` with no arguments must run the whole analysis on the bundled sample file "
              "`data/sample.csv` (a small realistic CSV the project ships, at least 8 rows, one deliberately "
              "bad row) and write its results into an `output/` folder it creates, then exit 0. Use the csv, "
              "statistics, json and datetime modules only (no pandas)."),
    spec={"code": [
        ("analysis", "backend", "Implement loading, cleaning and the analysis functions, and create the "
         "bundled sample dataset.", ["{pkg}/__init__.py", "{pkg}/analysis.py", "data/sample.csv"]),
        ("report", "frontend", "Implement {pkg}/report.py (render results) and {pkg}/__main__.py "
         "(the entry point described in the contract).", ["{pkg}/report.py", "{pkg}/__main__.py"]),
    ], "tests": "Write pytest tests for loading, cleaning and each analysis function using small CSVs in tmp_path.",
        "test_files": ["tests/test_analysis.py"]},
    required=("{pkg}/__main__.py", "data/sample.csv"),
    run_text="python -m {pkg}\n# results are written to output/",
    fix_defaults={"backend": "{pkg}/analysis.py", "frontend": "{pkg}/__main__.py", "qa": "tests/test_analysis.py"},
)

DATABASE = _py_profile(
    key="database", label="Database app", noun="database application",
    summary="A SQLite schema and query layer with a runnable demo.",
    example=("A school database application with students, courses and enrollments in SQLite. Provide "
             "functions to enrol and drop students, list a course roster, compute each student's average "
             "grade and find students with no enrollments, using parameterised queries."),
    contract=("`{pkg}/db.py` holds the schema and every query using the sqlite3 module with parameterised "
              "queries. `python -m {pkg}` runs a self-contained demo: create an in-memory database, seed it, "
              "run the main queries, print the results and exit 0."),
    spec={"code": [
        ("schema", "backend", "Implement the schema, connection helper and all query functions.",
         ["{pkg}/__init__.py", "{pkg}/db.py"]),
        ("demo", "frontend", "Implement {pkg}/__main__.py: the seeded demo described in the contract.",
         ["{pkg}/__main__.py"]),
    ], "tests": "Write pytest tests for every query function against an in-memory database with seed data.",
        "test_files": ["tests/test_db.py"]},
    required=("{pkg}/db.py", "{pkg}/__main__.py"),
    run_text="python -m {pkg}",
    fix_defaults={"backend": "{pkg}/db.py", "frontend": "{pkg}/__main__.py", "qa": "tests/test_db.py"},
)

GAME = _py_profile(
    key="game", label="Text game / simulator", noun="text game",
    summary="A rules engine with a terminal loop that reads commands from stdin.",
    example=("A text adventure game with several connected rooms, an inventory, items that unlock doors, a "
             "simple scoring system and commands like go, take, drop, use, look, inventory and quit."),
    contract=("The rules engine is a pure class in `{pkg}/game.py` with no input or output. "
              "`{pkg}/__main__.py` is the terminal loop: it reads one command per line from standard input, "
              "prints the result, and stops cleanly on the command `quit` or when input ends (EOF). "
              "`python -m {pkg}` must never wait forever once stdin is closed."),
    spec={"code": [
        ("engine", "backend", "Implement the rules engine: world, state, commands and scoring.",
         ["{pkg}/__init__.py", "{pkg}/game.py"]),
        ("terminal", "frontend", "Implement {pkg}/__main__.py: the stdin command loop from the contract.",
         ["{pkg}/__main__.py"]),
    ], "tests": "Write pytest tests that play scripted command sequences against the engine and check the state.",
        "test_files": ["tests/test_game.py"]},
    required=("{pkg}/game.py", "{pkg}/__main__.py"),
    run_text="python -m {pkg}      # type commands, `quit` to leave",
    fix_defaults={"backend": "{pkg}/game.py", "frontend": "{pkg}/__main__.py", "qa": "tests/test_game.py"},
)

AUTOMATION = _py_profile(
    key="automation", label="Automation script", noun="automation script",
    summary="A safe file-processing script with --dry-run, tested on temporary folders.",
    example=("A downloads folder organiser that sorts files into subfolders by type (images, documents, "
             "archives, other), skips files already in place, handles name clashes by adding a number, and "
             "has a dry-run mode that only prints what it would do."),
    contract=("`python -m {pkg}` accepts `--target PATH` (default: the current folder), `--dry-run` and "
              "`--apply`, and `--help`. Without `--apply` it only reports what it would do and changes "
              "nothing. The core logic lives in `{pkg}/` functions that take a Path so tests can run them on "
              "tmp_path."),
    frontend=True,
    spec={"code": [
        ("core", "backend", "Implement the file classification and move/plan logic.",
         ["{pkg}/__init__.py", "{pkg}/organizer.py"]),
        ("cli", "frontend", "Implement {pkg}/__main__.py: argument parsing and reporting from the contract.",
         ["{pkg}/__main__.py"]),
    ], "tests": "Write pytest tests that run the logic on temporary folders, in dry-run and apply modes.",
        "test_files": ["tests/test_organizer.py"]},
    required=("{pkg}/__main__.py",),
    run_text="python -m {pkg} --target <folder>          # dry run\npython -m {pkg} --target <folder> --apply",
    fix_defaults={"backend": "{pkg}/organizer.py", "frontend": "{pkg}/__main__.py", "qa": "tests/test_organizer.py"},
)

PROFILES: dict[str, Profile] = {p.key: p for p in (WEB, API, CLI, LIBRARY, DATA, DATABASE, GAME, AUTOMATION)}
DEFAULT_PROFILE = "web"


def get_profile(key: str | None) -> Profile:
    profile = PROFILES.get(key or DEFAULT_PROFILE)
    if profile is None:
        raise ValueError(f"unknown project type {key!r}; expected one of {sorted(PROFILES)}")
    return profile


__all__ = ["DEFAULT_PROFILE", "PROFILES", "PYTHON_RESERVED", "Profile", "get_profile",
           "WEB", "API", "CLI", "LIBRARY", "DATA", "DATABASE", "GAME", "AUTOMATION"]
