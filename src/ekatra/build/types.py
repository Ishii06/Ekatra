"""Small shared types for the build package (kept free of imports to avoid cycles)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlannedTask:
    key: str
    role: str
    description: str
    priority: int = 2
    complexity: int = 3
    risk: int = 20
    dependencies: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)


__all__ = ["PlannedTask"]
