"""Experiment record: a JSON-safe snapshot of one run.

The record separates RAW observations (timestamps, events, task/agent dicts)
from DERIVED metrics (``MetricsBundle``), so metrics can always be recomputed
from the persisted raw data.

Never holds API keys, secrets, or environment variables: it is constructed only
from run metadata and state summaries.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from ekatra.observability.metrics import MetricsBundle


def _json_default(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


@dataclass
class ExperimentRecord:
    """Single-run experiment record (fixed or adaptive strategy)."""

    run_id: str = field(default_factory=new_run_id)
    strategy: str = ""
    scenario_id: str = ""
    project_description: str = ""
    workflow_started_at: str | None = None
    workflow_completed_at: str | None = None
    task_summary: dict[str, Any] = field(default_factory=dict)
    agent_summary: dict[str, Any] = field(default_factory=dict)
    communication_summary: dict[str, Any] = field(default_factory=dict)
    tool_summary: dict[str, Any] = field(default_factory=dict)
    adaptive_summary: dict[str, Any] = field(default_factory=dict)
    quality_observations: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_metrics(
        cls,
        strategy: str,
        project_description: str,
        metrics: MetricsBundle,
        raw_events: list[dict[str, Any]],
        run_id: str | None = None,
        scenario_id: str | None = None,
    ) -> "ExperimentRecord":
        timing = metrics.timing
        quality = metrics.quality.get("observations") or []
        return cls(
            run_id=run_id or new_run_id(),
            strategy=strategy,
            scenario_id=scenario_id or "",
            project_description=project_description,
            workflow_started_at=timing.get("workflow_started_at"),
            workflow_completed_at=timing.get("workflow_completed_at"),
            task_summary=metrics.task,
            agent_summary=metrics.agent,
            communication_summary=metrics.communication,
            tool_summary=metrics.tools,
            adaptive_summary=metrics.adaptive,
            quality_observations=[
                {"timestamp": o.get("timestamp"), "category": o.get("category"),
                 "result": o.get("result"), "details": o.get("details")}
                for o in quality
            ],
            metrics=metrics.to_dict(),
            raw_events=raw_events,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy": self.strategy,
            "scenario_id": self.scenario_id,
            "project_description": self.project_description,
            "workflow_started_at": self.workflow_started_at,
            "workflow_completed_at": self.workflow_completed_at,
            "task_summary": self.task_summary,
            "agent_summary": self.agent_summary,
            "communication_summary": self.communication_summary,
            "tool_summary": self.tool_summary,
            "adaptive_summary": self.adaptive_summary,
            "quality_observations": self.quality_observations,
            "metrics": self.metrics,
            "raw_events": self.raw_events,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=_json_default, indent=2)

    @classmethod
    def from_json(cls, payload: str) -> "ExperimentRecord":
        return cls.from_dict(json.loads(payload))

    def to_csv(self) -> dict[str, str]:
        """Minimal CSV export: one file per table (tasks summary, events)."""
        tables: dict[str, str] = {}

        events = self.raw_events
        if events:
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer, fieldnames=["type", "timestamp", *sorted({
                    key for event in events for key in event if key not in ("type", "timestamp")
                })]
            )
            writer.writeheader()
            for event in events:
                writer.writerow({k: event.get(k, "") for k in writer.fieldnames})
            tables["events.csv"] = buffer.getvalue()

        if self.metrics.get("task"):
            rows = self.metrics["task"].get("task_completion_durations") or []
            if rows:
                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=sorted(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
                tables["task_durations.csv"] = buffer.getvalue()

        return tables

    def contains_secrets(self) -> bool:
        """Headless guard: the record must never reference settings/env secrets."""
        from ekatra.config.settings import get_settings

        settings = get_settings()
        payload = json.dumps(self.to_dict(), default=_json_default)
        return any(
            term and term != "" and term in payload
            for term in (settings.gemini_api_key,)
        )


__all__ = ["ExperimentRecord", "new_run_id"]