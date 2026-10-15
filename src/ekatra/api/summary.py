"""Shared run summaries for the REST API.

Workload and risk are derived from the engine's own observation helpers (the same
formulas the adaptive controller uses); nothing here is invented. The indicator
fractions describe the most loaded role, which is the role that sets the score.
"""

from __future__ import annotations

from typing import Any

from ekatra.orchestration import observe
from ekatra.orchestration.risk import RiskCalculator, RiskConfig
from ekatra.orchestration.workload import WorkloadCalculator, WorkloadConfig

_OUTSTANDING = ("PENDING", "ASSIGNED", "RUNNING", "RETRY")


def workload_and_risk(
    state: dict[str, Any],
    workload_config: WorkloadConfig | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the ``(workload, risk)`` summaries for a run state."""
    tasks = state.get("tasks", [])
    agents = state.get("agents", [])
    observation = observe(tasks, agents)
    workload_calc = WorkloadCalculator(workload_config or WorkloadConfig())
    risk_calc = RiskCalculator(RiskConfig())

    scored = [(workload_calc.score_for(obs), obs) for obs in observation.roles.values()]
    top_score, top = max(scored, key=lambda pair: pair[0]) if scored else (0.0, None)
    risk_score = risk_calc.score(observation.indicators)
    indicators = observation.indicators

    workload = {
        "score": round(top_score, 2),
        "level": workload_calc.level(top_score),
        "queueLength": sum(1 for t in tasks if t.get("status") in _OUTSTANDING),
        "complexity": round((top.avg_complexity if top else 0.0) / workload_calc.config.complexity_max, 3),
        "executionDelay": round(top.delay_ratio if top else 0.0, 3),
        "failureRate": round(top.failure_rate if top else 0.0, 3),
    }
    risk = {
        "score": round(risk_score, 2),
        "level": risk_calc.level(risk_score),
        "securityFindings": indicators.security_findings,
        "authIssues": indicators.auth_issues,
        "suspiciousCode": indicators.suspicious_code,
        "failedChecks": indicators.failed_security_checks,
        "repeatedFailures": indicators.task_failures,
        "highRiskTasks": indicators.high_risk_tasks,
    }
    return workload, risk


__all__ = ["workload_and_risk"]
