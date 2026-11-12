# Ekatra

Ekatra is an academic research prototype exploring **adaptive multi-agent
orchestration** for autonomous software development. It models a virtual
software-engineering organization of specialized AI agents and investigates
whether the agent organization can dynamically adapt its composition —
through spawning, termination, and reassignment — based on measurable
workload and risk during execution, rather than remaining statically fixed.

## Current Status

**Milestones 1–8 complete; real build mode added. Sprint 9 (analysis and report) in progress.**

Implemented so far:

* `src/` package skeleton (`config`, `state`, `graph`, `agents`, `tasks`,
  `orchestration`, `workspace`, `tools`, plus placeholder `utils` package)
* Environment-driven configuration (`GEMINI_API_KEY` — importable/testable
  without a real key, never logged)
* Shared workflow state as a lightweight `TypedDict`
* Agent abstraction (`Agent` base class, `Role`/`AgentStatus` enums) with six
  concrete role agents (Project Manager, Architect, Frontend, Backend, QA,
  Security) using deterministic mock or tool-assisted execution
* `FixedAgentPool` — the fixed baseline organization with exactly
  `PM-1`, `ARCH-1`, `FRONTEND-1`, `BACKEND-1`, `QA-1`, `SECURITY-1`
* Task model (`Task`, Pydantic) and deterministic `TaskManager` with validated
  lifecycle transitions (`PENDING → ASSIGNED → RUNNING → COMPLETED`,
  failure path `RUNNING → FAILED → RETRY → RUNNING` with retry counters),
  dependency validation, status queries, and serialization/restore
* Agent/task consistency: assignment updates both the task and the agent,
  agents go ACTIVE during execution and return to a non-active state after
* State snapshot helpers (`create_snapshot` / `snapshot_state`) producing
  JSON-safe plain data for logging, experiments, and metrics (no secrets)
* Structured agent communication:
  * `AgentMessage` (Pydantic) with a fixed `MessageType` set
  * In-memory `MessageBus` (deterministic, single-threaded): send/broadcast/
    read, per-agent inboxes, global history
  * Agents communicate through the bus during execution
  * Full message history accumulated in the state `communication` field
* Fixed LangGraph workflow (no dynamic routing — baseline untouched):

  ```
  START
    ↓
  project_manager
    ↓
  architect → backend → frontend → qa → security
    ↓
  END
  ```

* Adaptive orchestration controller (deterministic, no LLM):
  * `SystemObservation` / `RoleObservation` — structured workload + risk
    observation derived from task/agent state
  * `WorkloadCalculator` — weighted formula (queue, complexity, delay, failure)
    normalized to 0–100 with configurable thresholds (NORMAL / ELEVATED / HIGH)
  * `RiskCalculator` — six risk indicators normalized and weighted to 0–100
    (NORMAL / ELEVATED / HIGH)
  * `AdaptiveController` — deterministic decision cascade:
    SPAWN → SPAWN security → TERMINATE → REASSIGN → PRIORITIZE → CONTINUE
  * `AdaptiveDecision` — structured record with reason, scores, affected
    entities, and before/after state snapshots
  * `AdaptiveAgentPool` — dynamic pool with spawn/terminate on spawnable roles
    (BACKEND, FRONTEND, QA, SECURITY), baseline protection, max agents cap
  * `apply_decision` — applies decisions to pool + task manager, enriches
    decision records with outcomes
  * `TaskManager.set_priority` — priority updates with full `priority_history`
* Adaptive LangGraph workflow:

  ```
  START
    ↓
  adaptive_plan          ← PM plans, assigns baseline agents
    ↓
  adaptive_adapt         ← observe → controller → decision
    ↓
  adaptive_execute       ← execute pending tasks, reset to IDLE
    ↓
  remaining? ── yes ──→ adaptive_adapt
       │
       no → END
  ```

* Execution & tool integration (deterministic, workspace-bounded):
  * `Workspace` abstraction — a single root directory for the project; path
    resolution is normalized and containment-checked; `../` traversal and
    absolute paths escaping the root raise `PathTraversalError`
  * `Tool` interface + structured `ToolResult` (success, tool name, agent id,
    task id, output, error, ISO timestamp, duration) — every execution is
    observable, including failures
  * Built-in tools: `read_file`, `write_file`, `list_dir`, `inspect_path` —
    no shell/command execution tool (not needed by the current workflows)
  * Agents execute tasks with tools via `Agent.use_tool`; explicit per-role
    permissions in `tools.registry` (`RoleToolPolicy`): PM inspect-only, so
    write access is scoped (Architect/QA/Security → `docs/`, Backend →
    `backend/`, Frontend → `frontend/`)
  * Execution observability: every permitted tool call is accumulated in the
    state `tool_calls` field (agent, task, tool, success, duration, error)
  * Deterministic tool-assisted demo workflow:

  ```
  START
    ↓
  demo_plan        ← PM plans + inspects workspace
    ↓
  demo_architect → demo_backend → demo_frontend → demo_qa → demo_security
    ↓
  END
  ```

* Tests (359 passing, no real LLM calls or network)

* Observability & metrics layer (`src/ekatra/observability/`) — unified,
  strategy-agnostic measurement for BOTH the fixed baseline and the adaptive
  workflow (no metric logic duplicated across workflows):
  * `clock` — consistent ISO-8601 UTC timestamps; injectable `Clock`/`NowFn`
    for deterministic tests (task/tool events, workflow bounds)
  * `events` — the fixed, minimal set of 15 structured event types
    (`workflow_started/completed`, task lifecycle, agent spawn/termination,
    reassignment/prioritization, `adaptation_decision`, `tool_executed`,
    `quality_observation`); events are JSON-safe raw observations
  * `metrics` — one set of calculators (`compute_metrics`) deriving task,
    agent, communication, tool, quality, and adaptive metrics from the final
    state + raw event log; utilization = active time / available time with
    explicit baseline vs dynamically-spawned agent lifetime windows
  * `experiment` — secret-free JSON-safe experiment records (run id, strategy,
    summaries, derived metrics, raw events) with optional CSV export
  * All three workflows (fixed, adaptive, tool demo) emit the same raw event
    stream through `observability.integration` shared helpers

The adaptive controller is deterministic and separate from LLM reasoning. Planning and
code generation use Gemini only in the real build mode below; the experiments use
mock agents on a simulated clock.

## Build Real Software (Gemini)

Ekatra builds real software, not just websites. Gemini-driven agents plan the
project, write the files, QA writes and runs tests, Security reviews, and a repair
loop fixes what the checks find, orchestrated by the same fixed/adaptive strategies
the experiments evaluate.

| `--type` | What is built | How it is checked |
|---|---|---|
| `web` (default) | FastAPI backend serving an HTML/CSS/JS frontend | imports, assets, API contract, smoke test of the app |
| `api` | FastAPI REST service with documented routes | imports the app, calls every GET route, OpenAPI schema, `pytest` |
| `cli` | `argparse` tool with subcommands, run as `python -m <package>` | `--help` runs, `pytest` |
| `library` | importable package with a public API | `import <package>`, `pytest` |
| `data` | script that reads a bundled CSV and writes a report to `output/` | runs on the sample data, output exists, `pytest` |
| `database` | SQLite schema and query layer with a demo | runs the seeded demo, `pytest` |
| `game` | rules engine plus a terminal loop reading stdin | scripted session ends cleanly, `pytest` |
| `automation` | file-processing script with `--dry-run` / `--apply` | `--help` and a dry run on a sample folder, `pytest` |

```bash
# from the project root, with GEMINI_API_KEY and GEMINI_MODEL set in .env
set PYTHONPATH=src                      # PowerShell: $env:PYTHONPATH = "src"
python -m ekatra.build "A student wellbeing website with counsellor booking and a mood journal" --strategy adaptive
python -m ekatra.build "A command-line to-do manager with add, list, done, delete and stats" --type cli
```

The project is written to `projects/<name>-<type>-<strategy>-<id>/` (git-ignored);
its `README.md` says how to run it. Web projects use `backend/` and `frontend/`.
Every other type puts code in a package `<package>/` (named by the planner), tests in
`tests/`, documents in `docs/`.

How it works (`src/ekatra/build/`):

* **profiles** – `profiles.py` is the only place that knows what a project type looks
  like: file layout, which role may write where, the standards and plan rules given to
  agents, the fallback plan and the checks. The six agent roles, task manager,
  controller and metrics are identical for every type. For the Python types the Backend
  developer owns core logic, the Frontend developer owns the user-facing layer (command
  line, terminal loop, report rendering) when there is one, and **QA writes the pytest
  tests** (QA may write under `tests/` and `docs/` only).
* **plan** – the Project Manager asks Gemini for a task list (roles, dependencies,
  one owner per file, and for Python types the package name). The reply is validated
  (roles, dependency order, file ownership, required entry files, tests present, size)
  and a deterministic plan is used if it is unusable.
* **execute** – each agent makes one Gemini call and writes only its assigned
  files through the permission-checked workspace tools; path traversal is blocked.
  Failed attempts are retried with the previous error fed back to the model.
* **checks** – static: Python `ast` parse, package imports resolve, required files and
  tests exist (web also checks assets and the API contract). Runtime: the project's entry
  commands, then its own `pytest` suite, run in a separate Python process (project folder
  as working directory, API keys removed from the environment, hard timeouts). **This
  executes generated code.** Disable it with `--no-smoke-test` /
  `BuildConfig(smoke_test=False)`. QA's review is given this evidence.
* **repair** – QA/Security findings and check failures become fix tasks (two rounds by
  default, `--repair-rounds`), routed to the role that owns the failing file. A failing
  test creates a task for the code owner and one for QA, each told to change its side
  only if that side is wrong. Fix tasks may create missing modules/assets and see the
  other files of their area.
* **scheduling** – ready tasks run in parallel threads, at most
  `BuildConfig.max_concurrent_llm` Gemini requests at once. With `--strategy
  adaptive` the deterministic controller observes the real queue between
  completions and may SPAWN / TERMINATE / REASSIGN / PRIORITIZE agents; `fixed`
  keeps one agent per role. The LLM never controls spawning.
* **output** – `ekatra-run.json` in the project holds the tasks, events, adaptive
  decisions, metrics and run config (model name, thresholds; never the key).

Limits: the generated software is only as good as the model (`gemini-3.5-flash-lite`
is fast but sloppier than larger models), dead links and unfinished pages can
remain after the repair rounds, and the runtime checks exercise entry points, simple GET routes and the generated
tests, which can themselves be weak. Gemini rate limits (429) and overload (503) are retried with backoff.

### Change or fix a finished project

A finished project can be modified with a text request, from the dashboard (**Change or
fix this project** panel under the Build tab) or `POST /api/builds/{id}/changes`
(`{"request": "Add a dark mode toggle"}`). The Project Manager reads the file list and
`docs/architecture.md` and plans the smallest set of tasks (validated like any plan: roles,
write locations, one owner per file). Developers rewrite only their assigned files, QA
updates the tests, then the normal checks and repair rounds run, so a change that breaks
something is repaired or reported instead of hidden. Leave the text empty to only re-check
the project and repair what the checks find ("Fix remaining issues"). If a change cannot
be planned the project is left exactly as it was and the reason is shown. Each run is saved
as `ekatra-change-N.json` in the project folder. Projects found in `projects/` are restored
when the backend starts, so earlier builds can be changed after a restart.

## Backend API and Dashboard

```bash
# terminal 1 - backend (from the project root)
set PYTHONPATH=src                     # PowerShell: $env:PYTHONPATH = "src"
uvicorn ekatra.api.app:app --port 8000

# terminal 2 - dashboard
cd dashboard
npm install
npm run dev                            # http://localhost:3000
```

Restart the backend after pulling changes: a server started earlier keeps running the
old routes. The dashboard reads `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

Dashboard modes: **Demo** (scripted), **Experiment** (recorded M8 dataset), **Live Backend**
(a scenario run through the mock-agent workflows) and **Build** — type a website
description, press *Start build*, and watch the agents, spawns, tasks, controller
decisions and generated files appear live. Click a file to read it; when the build
finishes the panel shows validation issues, the commands to run the site, and a
**Run site** button that starts the generated backend on a free `127.0.0.1` port
(API keys stripped from its environment) and embeds the running site in a frame.

Build endpoints (`/api/builds`; one build may run at a time):

| Endpoint | Purpose |
|---|---|
| `POST /api/builds` `{description, strategy, repair_rounds, project_type}` | start a real build (needs `GEMINI_API_KEY`) |
| `GET /api/builds` | recent builds, newest first |
| `GET /api/builds/{id}` | full state: agents, tasks, decisions, workload, risk, metrics, events, files, log, issues |
| `GET /api/builds/{id}/stream` | Server-Sent Events: one state snapshot per change, then `event: done` |
| `GET /api/builds/{id}/files` / `.../files/{path}` | list / read generated files (confined to `backend/`, `frontend/`, `docs/`) |
| `GET /api/build-profiles` | the supported project types with a summary and an example description |
| `POST /api/builds/{id}/tests` / `.../demo` | run the generated project's `pytest` suite / demo command (Python types; executes generated code) |
| `POST` / `GET` / `DELETE /api/builds/{id}/launch` | run / check / stop a generated web app or API on localhost (executes generated code; at most 3 at once) |

Scenario endpoints (`/api/scenarios`, `/api/runs...`) are unchanged. Build state is kept in
memory, so it is lost when the backend restarts (the files in `projects/` remain).

## Experiments (simulated clock)

Fixed-vs-adaptive experiments use a deterministic **simulated clock**
(`src/ekatra/experiments/simulation.py`, ADR-007 pending): task durations and
failures are hash-seeded from `(scenario seed, repetition, task, attempt)`, so
both strategies face identical work and orchestration is the only difference.
`run_scenario`, `run_comparison` and `run_all_scenarios` default to
`engine="simulated"` (`engine="graph"` keeps the instant LangGraph workflows).
`evaluation_scenarios()` returns nine scenarios: the five M8 ones plus medium,
parallel-backlog, failure-heavy and risk-triage. Records store the full run
configuration. Quality metrics (test pass rate, defects, security issues) and
reliability metrics are derived from recorded events.

Not done yet: an experiment CLI, the analysis/graph script and the final report
(`docs/09-results.md`).

## Setup

Requires Python 3.13.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cp .env.example .env            # then add your GEMINI_API_KEY and GEMINI_MODEL
set PYTHONPATH=src              # the package is not pip-installed; PowerShell: $env:PYTHONPATH = "src"
```

## Run the Fixed Workflow

The workflow runs without any API key (agents use deterministic mock
execution; no LLM calls):

```bash
python -m ekatra.graph
```

or from Python:

```python
from ekatra.graph import run
from ekatra.state import snapshot_state

result = run({"project_description": "Build a todo app"})
print(result["tasks"])          # 5 completed tasks with assignments
print(result["messages"])       # agent messages (human-readable)
print(result["communication"])  # structured agent messages (bus history)
print(result["metrics"])        # simple metrics

snapshot = snapshot_state(result)  # JSON-safe task/agent snapshot
```

## Run the Adaptive Workflow

The adaptive workflow runs the observe → adapt → execute loop without any
API key:

```python
from ekatra.graph.adaptive import run_adaptive

result = run_adaptive("Build a todo app")
print(result["adaptive_decisions"])  # list of AdaptiveDecision records
print(result["tasks"])               # completed tasks
print(result["agents"])              # agent pool state
print(result["metrics"])             # includes adaptive_cycle
```

## Run the Tests

```bash
pytest
```

## Run the Tool-Assisted Demo Workflow

The demo runs the deterministic tool-assisted workflow inside a temporary
workspace (no API key, no shell execution). It prints an observable summary of
the tool executions:

```bash
python -m ekatra.graph.tools
```

```python
from ekatra.graph.tools import run_tools_demo, summarize

result = run_tools_demo("Build a todo app", "path/to/workspace")
print(summarize(result))   # tasks, tool calls, per-tool/per-agent counts
print(result["tool_calls"])  # structured execution observability records
```

## Derive Metrics & Experiment Records

The raw event stream accumulated in `state["observability_events"]` and the
unified calculators produce one identical metric schema for every strategy:

```python
from ekatra.graph import run
from ekatra.observability.metrics import compute_metrics
from ekatra.observability.experiment import ExperimentRecord

result = run({"project_description": "Build a todo app"})
metrics = compute_metrics(result)          # same schema for fixed/adaptive
print(metrics.task["completed_tasks"])     # task totals & durations
print(metrics.agent["agent_utilization"])  # active time / available time

record = ExperimentRecord.from_metrics(
    "fixed", "Build a todo app", metrics, result["observability_events"]
)
json.dump(record.to_dict(), open("experiment.json", "w"))
```

Raw observations (events, task timestamps) are always preserved alongside the
derived metrics so results can be recomputed from the log alone.

## Run the Scenario Experiment Harness (Milestone 8)

The harness runs identical controlled scenarios under the fixed and adaptive
strategies and produces one M7 `ExperimentRecord` per run. No winner is
computed and no statistics are attempted — the output is descriptive and
reproducible.

The five built-in scenarios live in `src/ekatra/experiments/fixtures.py`:
`low_workload`, `high_backend_workload`, `high_frontend_workload`,
`security_risk`, and `mixed_high_workload`. Each returns a single shared
scenario object (task set, project description, timing seed, expected
characteristics); the runner rebuilds identical task dicts from it for both
strategies.

```python
from ekatra.experiments import low_workload, run_all_scenarios, run_comparison, run_scenario

records = run_scenario(low_workload(), "fixed", repetitions=1)
print(records[0].to_dict()["metrics"]["task"]["completed_tasks"])

comparison = run_comparison(low_workload(), repetitions=1)
dataset = run_all_scenarios(repetitions=1)

import json
json.dump(dataset, open("ekatra_m8_dataset.json", "w"))
```

`run_all_scenarios()` returns a JSON-serializable dataset preserving
scenario metadata, per-strategy records, run ids, metrics, and the raw
observability event streams. Deterministic task ids are assigned in scenario
declaration order; `timing.base_timestamp` pins task creation timestamps so
adopted task sets are byte-identical across strategies.

Background and design rationale: `docs/decisions/ADR-005-scenario-seeding.md`.