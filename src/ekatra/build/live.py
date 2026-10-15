"""Real build mode: agents use Gemini to build an actual website.

The same orchestration that the experiments evaluate drives a real project:

* the Project Manager plans the work with Gemini (validated, with a fallback);
* a live scheduler dispatches ready tasks to idle agents, each running its Gemini
  call in its own thread, on the wall clock;
* with ``strategy="adaptive"`` the deterministic controller observes the real task
  queue between completions and may SPAWN / TERMINATE / REASSIGN / PRIORITIZE;
  with ``strategy="fixed"`` it never runs (one agent per role);
* QA and Security review the result; a bounded repair round turns their findings
  and the static-validation findings into fix tasks;
* every event, decision and metric uses the same schema as the experiments.

Scheduling reuses the experiment engine's dispatch/adapt logic (only the clock and
the executor differ). The LLM never controls spawning or termination.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ekatra.agents.base import AgentStatus, Role
from ekatra.build.execute import TaskOutcome, execute_task
from ekatra.build.plan import LLMFn, PlannedTask, plan_project
from ekatra.build.smoke import smoke_test
from ekatra.build.validate import Issue, validate_project
from ekatra.experiments.simulation import SimConfig, _Simulation
from ekatra.observability.experiment import ExperimentRecord
from ekatra.observability.integration import (
    quality_observation_event,
    task_assigned_event,
    task_completed_event,
    task_created_event,
    task_failed_event,
    task_retried_event,
    task_started_event,
    workflow_completed_event,
    workflow_started_event,
)
from ekatra.observability.metrics import MetricsBundle, compute_metrics
from ekatra.orchestration.controller import AdaptiveController, ControllerConfig
from ekatra.orchestration.pool import _BASELINE_IDS, AdaptiveAgentPool
from ekatra.orchestration.workload import WorkloadConfig
from ekatra.tasks.manager import TaskManager
from ekatra.workspace import Workspace

Progress = Callable[[str], None]
Update = Callable[[dict[str, Any]], None]

# Real builds have short queues (a few tasks per role), so the controller uses
# lower workload thresholds than the 10-task experiment scale. These are
# recorded in the run's config.
LIVE_WORKLOAD = WorkloadConfig(queue_reference=4, continue_below=30.0, monitor_below=55.0)


@dataclass(frozen=True)
class BuildConfig:
    """Parameters of a real build."""

    max_retries: int = 3
    repair_rounds: int = 2
    smoke_test: bool = True  # run the generated app once (executes generated code)
    max_agents_per_role: int = 3
    max_workers: int = 12
    max_concurrent_llm: int = 2  # parallel Gemini requests (provider rate limits)


class LiveClock:
    """Wall clock exposing the same interface as the simulated clock."""

    def __init__(self) -> None:
        self.base = datetime.now(timezone.utc)
        self._t0 = time.monotonic()

    @property
    def t(self) -> float:
        return time.monotonic() - self._t0

    def datetime(self) -> datetime:
        return self.base + timedelta(seconds=self.t)

    def iso(self) -> str:
        return self.datetime().isoformat()


@dataclass
class BuildResult:
    root: Path
    strategy: str
    plan_source: str
    state: dict[str, Any]
    metrics: MetricsBundle
    final_issues: list[Issue] = field(default_factory=list)

    @property
    def success(self) -> bool:
        tasks = self.state["tasks"]
        return bool(tasks) and all(t["status"] == "COMPLETED" for t in tasks) and not any(
            i["severity"] == "high" for i in self.final_issues
        )


class _LiveBuild(_Simulation):
    """Live scheduler; inherits dispatch/adapt from the experiment engine."""

    def __init__(
        self,
        description: str,
        strategy: str,
        workspace: Workspace,
        llm: LLMFn,
        cfg: BuildConfig,
        progress: Progress,
        on_update: Update | None = None,
    ) -> None:
        if strategy not in ("fixed", "adaptive"):
            raise ValueError(f"unknown strategy {strategy!r}; expected 'fixed' or 'adaptive'")
        self.description = description
        self.strategy = strategy
        self.workspace = workspace
        self.llm = llm
        self.cfg = cfg
        self.log = progress
        self.on_update = on_update
        self.plan_source = ""
        self.final_issues: list[Issue] = []
        self.sim = SimConfig(spawn_overhead=0.0, max_retries=cfg.max_retries)
        self.clock = LiveClock()
        self.manager = TaskManager(now_fn=self.clock.datetime)
        self.pool = AdaptiveAgentPool()
        self.available_at: dict[str, float] = {}
        self.wakes: list[float] = []
        self.finishes: list = []
        self.seq = 0
        self.attempts: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.cycle = 0
        self.futures: dict[Future, tuple[str, str]] = {}
        self.planned: dict[str, PlannedTask] = {}
        self.key_to_id: dict[str, str] = {}
        self.fix_issues: dict[str, list[Issue]] = {}
        self.review_issues: list[Issue] = []
        self.errors: dict[str, str] = {}
        self.controller_config = ControllerConfig(
            workload=LIVE_WORKLOAD,
            max_agents_per_role=cfg.max_agents_per_role,
            now=self.clock.iso,
        )
        self.controller = AdaptiveController(self.controller_config)
        self.executor: ThreadPoolExecutor | None = None

    def publish(self) -> None:
        """Hand a fresh, consistent state snapshot to the observer (driver thread only)."""
        if self.on_update is not None:
            self.on_update(self._final_state())

    # -- planning ---------------------------------------------------------------

    def create_tasks(self, plan: list[PlannedTask]) -> None:
        self.events.append(workflow_started_event(self.description, self.clock.iso()))
        for pt in plan:
            task = self.manager.create(
                role=Role(pt.role), description=pt.description, priority=pt.priority,
                complexity=pt.complexity, risk=pt.risk,
                dependencies=[self.key_to_id[d] for d in pt.dependencies],
            )
            self.planned[task.id] = pt
            self.key_to_id[pt.key] = task.id
            self.events.append(task_created_event(task.to_dict()))
        for task in self.manager.all():
            self.manager.assign(task.id, _BASELINE_IDS[task.role])
            self.events.append(task_assigned_event(task.to_dict()))
        self.publish()

    # -- execution --------------------------------------------------------------

    def _start(self, task_id: str, agent: Any) -> None:
        self.manager.start(task_id)
        self.attempts[task_id] = self.attempts.get(task_id, 0) + 1
        agent.status = AgentStatus.ACTIVE
        agent.current_task = task_id
        if agent.workspace is None:
            agent.attach_workspace(self.workspace)
        self.events.append(task_started_event(self._task(task_id)))
        planned = self.planned[task_id]
        deps = [d for key in planned.dependencies for d in self.planned[self.key_to_id[key]].deliverables]
        if planned.key.startswith("fix_"):  # fixers need to see the rest of their area
            prefix = planned.role + "/"
            deps += [p for p in self.workspace.list_files(".") if p.startswith(prefix) and p.endswith((".py", ".js", ".html", ".css"))]
        future = self.executor.submit(
            execute_task, agent, task_id, planned,
            workspace=self.workspace, description=self.description, llm=self.llm,
            fix_issues=self.fix_issues.get(task_id), dependency_paths=deps + planned.deliverables,
            previous_error=self.errors.get(task_id, ""),
        )
        self.futures[future] = (task_id, agent.agent_id)
        self.log(f"  [{self.clock.t:6.1f}s] {agent.agent_id:<11} started   {planned.key}")
        self.publish()

    def _complete(self, future: Future) -> None:
        task_id, agent_id = self.futures.pop(future)
        agent = self.pool.get(agent_id)
        agent.status = AgentStatus.IDLE
        agent.current_task = None
        planned = self.planned[task_id]
        try:
            outcome: TaskOutcome = future.result()
        except Exception as exc:  # noqa: BLE001 - executor failure
            outcome = TaskOutcome(False, error=f"{type(exc).__name__}: {exc}")
        task = self.manager.get(task_id)
        if outcome.ok:
            self.manager.complete(task_id, output=outcome.summary)
            snapshot = self._task(task_id)
            self.events.append(task_completed_event(snapshot))
            self.log(f"  [{self.clock.t:6.1f}s] {agent_id:<11} finished  {planned.key}: {outcome.summary[:90]}")
            if planned.role in ("qa", "security"):
                self.review_issues.extend(outcome.issues)
                if planned.role == "qa":
                    high = any(i["severity"] == "high" for i in outcome.issues)
                    self.events.append(quality_observation_event("tests", "fail" if high else "pass", snapshot))
                    self.events.append(quality_observation_event(
                        "defects_detected", "found", snapshot, count=len(outcome.issues)))
                else:
                    self.events.append(quality_observation_event(
                        "security_issues_identified", "found", snapshot, count=len(outcome.issues)))
            self.publish()
            return
        self.errors[task_id] = outcome.error
        self.manager.fail(task_id, reason=outcome.error)
        self.events.append(task_failed_event(self._task(task_id), self.clock.iso()))
        self.log(f"  [{self.clock.t:6.1f}s] {agent_id:<11} FAILED    {planned.key}: {outcome.error[:240]}")
        if task.retry_count < self.cfg.max_retries:
            self.manager.retry(task_id)
            self.events.append(task_retried_event(self._task(task_id), self.clock.iso()))
        self.publish()

    def drive(self) -> None:
        """Run until no task can make progress."""
        while True:
            if self.strategy == "adaptive":
                before = len(self.decisions)
                self.adapt()
                for d in self.decisions[before:]:
                    if d["decision"] != "CONTINUE":
                        self.log(f"  [{self.clock.t:6.1f}s] controller  {d['decision']}: {d['reason'][:110]}")
                if len(self.decisions) > before:
                    self.publish()
            self.dispatch()
            if not self.futures:
                self._cancel_unreachable()
                return
            done, _ = wait(list(self.futures), return_when=FIRST_COMPLETED)
            for future in done:
                self._complete(future)

    # -- repair ------------------------------------------------------------------

    def schedule_repairs(self, round_no: int) -> bool:
        """Create one fix task per developer role that has open high/medium issues."""
        found = self.review_issues + self.check_project()
        issues = [i for i in found if i["severity"] in ("high", "medium")]
        created = False
        for owner in ("backend", "frontend"):
            mine = [i for i in issues if i["owner"] == owner]
            wanted = {i["file"] for i in mine
                      if i["file"].startswith(owner + "/") and self.workspace.exists(i["file"])}
            wanted |= {i["missing_file"] for i in mine
                       if i.get("missing_file", "").startswith(owner + "/")}
            files = sorted(wanted)[:8]
            if not mine:
                continue
            if not files:
                files = ["backend/main.py"] if owner == "backend" else ["frontend/index.html"]
            key = f"fix_{owner}_{round_no}"
            task = self.manager.create(
                role=Role(owner), description=f"Fix review findings in {', '.join(files)}",
                priority=3, complexity=3, risk=30,
            )
            self.planned[task.id] = PlannedTask(key, owner, task.description, 3, 3, 30, [], files)
            self.key_to_id[key] = task.id
            self.fix_issues[task.id] = mine[:12]
            self.manager.assign(task.id, _BASELINE_IDS[task.role])
            self.events.append(task_created_event(task.to_dict()))
            self.events.append(task_assigned_event(task.to_dict()))
            self.log(f"  repair round {round_no}: {owner} fix task for {len(mine)} issue(s) in {', '.join(files)}")
            created = True
        self.review_issues = []
        if created:
            self.publish()
        return created

    def check_project(self) -> list[Issue]:
        """Static validation plus (optionally) the runtime smoke test."""
        issues = validate_project(self.workspace.root)
        if self.cfg.smoke_test and not any(i["severity"] == "high" and i["file"] == "backend/main.py"
                                           and "missing" in i["description"] for i in issues):
            self.log("  smoke-testing the generated app...")
            issues += smoke_test(self.workspace.root)
        return issues

    # -- finish ------------------------------------------------------------------

    def finish(self) -> list[Issue]:
        if self.strategy == "adaptive":
            self.adapt()  # release idle spawned agents now that work has drained
        issues = self.check_project()
        high = [i for i in issues if i["severity"] == "high"]
        self.events.append(quality_observation_event(
            "final_validation", "fail" if high else "pass", {"id": "PROJECT"},
            count=len(issues), timestamp=self.clock.iso()))
        self.events.append(workflow_completed_event("build", self.clock.iso()))
        self.final_issues = issues
        self.publish()
        return issues

    def _final_state(self) -> dict[str, Any]:
        tool_calls = [
            r.to_dict() for a in self.pool._agents.values() for r in a.tool_calls
        ]
        return {
            "project_description": self.description,
            "tasks": self.manager.to_dicts(),
            "agents": self.pool.to_dicts(include_terminated=True),
            "current_step": "build",
            "messages": [],
            "communication": [],
            "metrics": {},
            "adaptive_decisions": self.decisions,
            "adaptive_cycle": self.cycle,
            "tool_calls": tool_calls,
            "observability_events": self.events,
            "plan_source": self.plan_source,
            "final_issues": self.final_issues,
        }


_README = """# {title}

Built by Ekatra ({strategy} orchestration) from this description:

> {description}

## Run it

```bash
python -m venv .venv
.venv\\Scripts\\activate        # Windows (use `source .venv/bin/activate` elsewhere)
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000

## Files

{files}

Design notes are in `docs/architecture.md`; the QA and security reports are in `docs/`.
`ekatra-run.json` holds the run's tasks, agent events, adaptive decisions and metrics.
"""


def build_project(
    description: str,
    *,
    out_dir: str | Path,
    strategy: str = "adaptive",
    llm: LLMFn | None = None,
    config: BuildConfig | None = None,
    progress: Progress | None = None,
    on_update: Update | None = None,
) -> BuildResult:
    """Build a website for ``description`` into ``out_dir`` with Gemini-driven agents."""
    if llm is None:
        from ekatra.llm.gemini import generate

        def llm(prompt: str, json_mode: bool) -> str:  # noqa: F811
            return generate(prompt, json_mode=json_mode, max_output_tokens=32768)

    cfg = config or BuildConfig()
    log = progress or (lambda message: None)
    raw_llm, gate = llm, threading.BoundedSemaphore(max(1, cfg.max_concurrent_llm))

    def llm(prompt: str, json_mode: bool) -> str:  # noqa: F811 - rate-limited wrapper
        with gate:
            return raw_llm(prompt, json_mode)

    workspace = Workspace(out_dir)
    log(f"Planning with the Project Manager ({strategy} strategy)...")
    plan, plan_source = plan_project(description, llm)
    log(f"Plan ({plan_source}): {len(plan)} tasks")
    for pt in plan:
        log(f"  - {pt.key} [{pt.role}] -> {', '.join(pt.deliverables)}")

    build = _LiveBuild(description, strategy, workspace, llm, cfg, log, on_update)
    build.plan_source = plan_source
    build.create_tasks(plan)
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        build.executor = executor
        build.drive()
        for round_no in range(1, cfg.repair_rounds + 1):
            if not build.schedule_repairs(round_no):
                break
            build.drive()
    issues = build.finish()

    state = build._final_state()
    metrics = compute_metrics(state)
    files = sorted(p for p in workspace.list_files(".") if p.split("/")[0] in {"backend", "frontend", "docs"})
    workspace.write_text("requirements.txt", "fastapi\nuvicorn[standard]\n")
    workspace.write_text("README.md", _README.format(
        title=description.split(".")[0][:70], strategy=strategy, description=description,
        files="\n".join(f"- `{p}`" for p in files)))
    record = ExperimentRecord.from_metrics(
        strategy, description, metrics, state["observability_events"],
        run_id=f"build-{strategy}-{int(time.time())}", scenario_id="live_build",
        config={
            "engine": "live", "strategy": strategy, "plan_source": plan_source,
            "build": cfg.__dict__, "workload": LIVE_WORKLOAD.model_dump(),
            "max_agents_per_role": cfg.max_agents_per_role,
            "model": _model_config(),
        },
    )
    import json
    workspace.write_text("ekatra-run.json", json.dumps({
        **record.to_dict(), "tasks": state["tasks"], "agents": state["agents"],
        "decisions": state["adaptive_decisions"], "final_issues": issues, "errors": build.errors,
    }, indent=2, default=str))
    return BuildResult(workspace.root, strategy, plan_source, state, metrics, issues)


def _model_config() -> dict[str, Any]:
    from ekatra.config.settings import get_settings

    settings = get_settings()
    return {"provider": settings.llm_provider, "name": settings.gemini_model,
            "temperature": settings.model_temperature}


__all__ = ["BuildConfig", "BuildResult", "LIVE_WORKLOAD", "LiveClock", "build_project"]
