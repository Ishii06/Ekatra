"""Milestone 7: unified observability & metrics layer.

Measurement infrastructure for BOTH the fixed baseline and the adaptive
workflow. Kept deliberately independent from agent reasoning, task management,
adaptive decision logic, and tool execution: workflows only append raw events
(``integration.py``) and the same calculators (``metrics.py``) derive unified,
strategy-agnostic metrics. ``experiment.py`` packages one run (raw events +
derived metrics) into a secret-free, JSON-safe record.
"""

from ekatra.observability.clock import Clock, default_now, parse_ts, seconds_between
from ekatra.observability.events import Event, EventLog, EventType, make_event
from ekatra.observability.experiment import ExperimentRecord, new_run_id
from ekatra.observability.metrics import MetricsBundle, compute_metrics

__all__ = [
    "Clock",
    "Event",
    "EventLog",
    "EventType",
    "ExperimentRecord",
    "MetricsBundle",
    "compute_metrics",
    "default_now",
    "make_event",
    "new_run_id",
    "parse_ts",
    "seconds_between",
]