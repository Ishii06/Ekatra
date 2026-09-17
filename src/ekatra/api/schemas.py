from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ScenarioResponse(BaseModel):
    scenario_id: str
    name: str
    description: str
    project_description: str
    task_count: int
    expected_characteristics: dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    scenario_id: str
    strategy: str = Field(..., pattern="^(fixed|adaptive)$")


class RunResponse(BaseModel):
    run_id: str
    scenario_id: str
    strategy: str
    status: str


class RunStateResponse(BaseModel):
    run_id: str
    scenario_id: str
    strategy: str
    status: str
    agents: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    adaptive_decisions: list[dict[str, Any]] = Field(default_factory=list)
    workload: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    communication: list[dict[str, Any]] = Field(default_factory=list)
    tool_summary: dict[str, Any] = Field(default_factory=dict)
    observability_events: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    project_state: str = "PLANNING"
    error: str | None = None
