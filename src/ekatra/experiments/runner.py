"""Milestone 8: experiment runner.

Runs the same scenario under the fixed and adaptive strategies and produces an
M7 :class:`~ekatra.observability.experiment.ExperimentRecord` per repetition.

Design notes:

* ``build_initial_state`` rebuilds identical task dicts from the scenario for
  both strategies, so orchestration strategy is the only experimental variable.
* Runs reuse the existing workflow entry points
  (``graph/__main__.run`` and ``graph/adaptive.run_adaptive``) and M7
  ``compute_metrics`` / ``ExperimentRecord``.
* No winner is computed, no statistics are performed; the harness is purely
  descriptive and reproducible.
* Secret hygiene: metrics and records exclude any value whose key or content
  is an API credential; scenario validation also forbids secret-looking
  content.
"""

from __future__ import annotations

from typing import Any, Callable

from ekatra.experiments.scenarios import ExperimentScenario
from ekatra.graph import run
from ekatra.graph.adaptive import run_adaptive
from ekatra.observability.experiment import ExperimentRecord
from ekatra.observability.metrics import compute_metrics
from ekatra.state.state import EkatraState

def build_initial_state(scenario: ExperimentScenario) -> EkatraState:
    """Build the initial workflow state for a scenario.

    The scenario's task set is materialized once into deterministic task-state
    dicts and stored under the existing ``tasks`` field; the workflows adopt
    them during planning (Milestone 8 seeded adoption).
    """
    base_timestamp = (scenario.timing or {}).get("base_timestamp")
    state = {
        "project_description": scenario.project_description,
        "tasks": scenario.resolve_tasks(base_timestamp=base_timestamp),
        "current_step": "project_manager",
        "agents": [],
        "messages": [],
        "communication": [],
        "metrics": {},
        "adaptive_decisions": [],
        "observability_events": [],
    }
    return state


def _run_once(scenario: ExperimentScenario, strategy: str) -> EkatraState:
    state = build_initial_state(scenario)
    if strategy == "fixed":
        return run(state)
    if strategy == "adaptive":
        state["adaptive_cycle"] = 1
        return run_adaptive(initial_state=state)
    raise ValueError(f"unknown strategy {strategy!r}; expected 'fixed' or 'adaptive'")


def run_scenario(
    scenario: ExperimentScenario,
    strategy: str = "fixed",
    repetitions: int = 1,
    run_ids: list[str] | None = None,
) -> list[ExperimentRecord]:
    """Run a scenario under a strategy one or more times.

    Args:
        scenario: The shared scenario object to execute.
        strategy: ``"fixed"`` or ``"adaptive"``.
        repetitions: How many independent runs to execute.
        run_ids: Optional explicit run ids (one per repetition); defaults to
            deterministic ``"{scenario_id}-{strategy}-{n}"`` ids.

    Returns:
        One M7 experiment record per repetition.
    """
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if run_ids is not None and len(run_ids) != repetitions:
        raise ValueError("run_ids must provide one per repetition")

    records: list[ExperimentRecord] = []
    for n in range(repetitions):
        run_id = run_ids[n] if run_ids else f"{scenario.scenario_id}-{strategy}-{n + 1}"
        final_state = _run_once(scenario, strategy)
        metrics = compute_metrics(final_state)
        raw_events = final_state.get("observability_events", [])
        records.append(
            ExperimentRecord.from_metrics(
                strategy=strategy,
                project_description=scenario.project_description,
                metrics=metrics,
                raw_events=raw_events,
                run_id=run_id,
                scenario_id=scenario.scenario_id,
            )
        )
    return records


def run_comparison(
    scenario: ExperimentScenario,
    repetitions: int = 1,
) -> dict[str, Any]:
    """Run a scenario under both strategies and group the records by strategy.

    Returns:
        ``{"scenario": <scenario dict>, "fixed": [...], "adaptive": [...]}``.
        Each strategy list holds ``ExperimentRecord.to_dict()`` entries, one
        per repetition.
    """
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    return {
        "scenario": scenario.to_dict(),
        "fixed": [r.to_dict() for r in run_scenario(scenario, "fixed", repetitions)],
        "adaptive": [r.to_dict() for r in run_scenario(scenario, "adaptive", repetitions)],
    }


def run_all_scenarios(
    scenarios: list[ExperimentScenario] | None = None,
    repetitions: int = 1,
) -> dict[str, Any]:
    """Run every scenario under both strategies and return a dataset.

    Returns a JSON-serializable dataset keyed by scenario id that preserves
    scenario metadata, per-strategy records with their run ids, metrics, and
    raw observability events. No database or external telemetry is used.
    """
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    from ekatra.experiments.fixtures import all_scenarios

    selected = scenarios if scenarios is not None else all_scenarios()
    return {
        "dataset": "ekatra_m8_scenario_dataset",
        "version": 1,
        "repetitions": repetitions,
        "scenarios": {
            scenario.scenario_id: run_comparison(scenario, repetitions)
            for scenario in selected
        },
    }


__all__ = [
    "build_initial_state",
    "run_all_scenarios",
    "run_comparison",
    "run_scenario",
]