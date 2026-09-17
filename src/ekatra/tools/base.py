"""Tool interface and structured execution result.

A :class:`Tool` is a small, deterministic, observable unit of work executed on
behalf of an agent. Every tool:

* has a stable ``name`` and human-readable ``description``
* validates its inputs before execution
* runs deterministically inside a bounded :class:`~ekatra.workspace.Workspace`
* returns a structured :class:`ToolResult` with success/failure, timing, and
  enough metadata for later evaluation

Tools never log secrets — the result payload carries output/error only.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ekatra.workspace import Workspace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolError(RuntimeError):
    """Base error raised by tool input validation / execution."""


class ToolResult(BaseModel):
    """Structured outcome of a single tool execution.

    Attributes:
        success: Whether the tool completed successfully.
        tool_name: The name of the tool that ran.
        output: The tool's payload (content, path list, metadata, ...).
        error: Human-readable failure message when not successful.
        agent_id: Optional agent that invoked the tool.
        task_id: Optional task that triggered the tool.
        timestamp: ISO-8601 UTC execution timestamp.
        duration_ms: Measured wall-clock duration of the execution.
        metadata: Free-form JSON-safe supplementary observability data.
    """

    success: bool
    tool_name: str
    output: Any = None
    error: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    timestamp: str = Field(default_factory=_now_iso)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for state accumulation."""
        return self.model_dump(mode="json")


class Tool:
    """Base class for workspace-bounded execution tools."""

    name: str = "tool"
    description: str = ""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def execute(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        **params: Any,
    ) -> ToolResult:
        """Validate and run the tool, always returning a structured result.

        Any exception raised by validation or execution is captured and
        reported inside the :class:`ToolResult` rather than propagated, so the
        caller always receives an observable outcome.
        """
        started = time.perf_counter()
        try:
            validated = self.validate(**params)
            output = self.run(**validated)
            duration_ms = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                success=True,
                tool_name=self.name,
                output=output,
                agent_id=agent_id,
                task_id=task_id,
                duration_ms=round(duration_ms, 3),
            )
        except Exception as exc:  # noqa: BLE001 - captured as observable result
            duration_ms = (time.perf_counter() - started) * 1000.0
            return ToolResult(
                success=False,
                tool_name=self.name,
                error=str(exc),
                agent_id=agent_id,
                task_id=task_id,
                duration_ms=round(duration_ms, 3),
            )

    def validate(self, **params: Any) -> dict[str, Any]:
        """Validate and normalize keyword inputs. Subclasses may override."""
        return params

    def run(self, **params: Any) -> Any:
        """Execute the tool after validation. Subclasses must override."""
        raise NotImplementedError


__all__ = ["Tool", "ToolError", "ToolResult", "_now_iso"]