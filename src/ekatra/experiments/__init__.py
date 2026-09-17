"""Milestone 8: deterministic experiment harness.

The harness runs the same controlled scenarios under the two orchestration
strategies (fixed baseline and adaptive controller) and records every run as an
M7 :class:`~ekatra.observability.experiment.ExperimentRecord`.

A scenario is a single shared, serializable input (project description + task
set + timing metadata + expected characteristics). The runner rebuilds
identical task dicts from the scenario for both strategies, so orchestration
strategy is the only experimental variable. No winner is ever computed and no
statistical analysis is performed.
"""

from ekatra.experiments.fixtures import (
    high_backend_workload,
    high_frontend_workload,
    low_workload,
    mixed_high_workload,
    security_risk,
)
from ekatra.experiments.runner import (
    run_all_scenarios,
    run_comparison,
    run_scenario,
)
from ekatra.experiments.scenarios import ExperimentScenario, ExperimentTask

__all__ = [
    "ExperimentScenario",
    "ExperimentTask",
    "high_backend_workload",
    "high_frontend_workload",
    "low_workload",
    "mixed_high_workload",
    "run_all_scenarios",
    "run_comparison",
    "run_scenario",
    "security_risk",
]