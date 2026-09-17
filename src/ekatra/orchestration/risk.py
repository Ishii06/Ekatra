"""Deterministic risk model.

Computes a project risk score on a 0-100 scale from measurable indicators
(``docs/04-adaptive-orchestration.md``):

* security findings
* failed security checks
* authentication / authorization issues
* suspicious code indicators
* repeated task failures
* high-risk tasks

Each indicator count is normalized to 0-100 against a configurable reference
count (``indicator_reference``) and combined with configurable weights. The
weights and thresholds are experimental parameters, not validated constants;
no claim is made that they represent optimal real-world risk estimation.
"""

from __future__ import annotations

from pydantic import BaseModel

from ekatra.orchestration._scoring import clamp100


class RiskConfig(BaseModel):
    """Configuration for the experimental risk model.

    Attributes:
        weight_security_findings: Weight for security findings (default 0.25).
        weight_failed_security_checks: Weight for failed security checks
            (default 0.15).
        weight_auth_issues: Weight for auth/authz issues (default 0.15).
        weight_suspicious_code: Weight for suspicious code (default 0.10).
        weight_task_failures: Weight for repeated task failures (default 0.20).
        weight_high_risk_tasks: Weight for high-risk tasks (default 0.15).
        indicator_reference: Indicator count saturating a component (default 10).
        high_risk_task_threshold: Task ``risk`` value treated as high risk.
        elevated_threshold: Scores below this are normal-risk.
        high_threshold: Scores below this (and at/above elevated) are elevated.
    """

    weight_security_findings: float = 0.25
    weight_failed_security_checks: float = 0.15
    weight_auth_issues: float = 0.15
    weight_suspicious_code: float = 0.10
    weight_task_failures: float = 0.20
    weight_high_risk_tasks: float = 0.15
    indicator_reference: int = 10
    high_risk_task_threshold: int = 70
    elevated_threshold: float = 40.0
    high_threshold: float = 70.0

    def validated_weights(self) -> tuple[float, float, float, float, float, float]:
        """Return the six component weights after clamping each to [0, 1]."""
        return (
            max(0.0, min(1.0, self.weight_security_findings)),
            max(0.0, min(1.0, self.weight_failed_security_checks)),
            max(0.0, min(1.0, self.weight_auth_issues)),
            max(0.0, min(1.0, self.weight_suspicious_code)),
            max(0.0, min(1.0, self.weight_task_failures)),
            max(0.0, min(1.0, self.weight_high_risk_tasks)),
        )


class RiskIndicators(BaseModel):
    """Measured risk indicator counts derived from the system state."""

    security_findings: int = 0
    failed_security_checks: int = 0
    auth_issues: int = 0
    suspicious_code: int = 0
    task_failures: int = 0
    high_risk_tasks: int = 0


def normalized_indicator(indicators: RiskIndicators, config: RiskConfig) -> dict[str, float]:
    """Normalize each indicator count to a 0-100 component score.

    Assumption (documented): a component saturates (100) once its count reaches
    ``indicator_reference`` (default 10) occurrences.
    """
    reference = config.indicator_reference
    if reference <= 0:
        raise ValueError("indicator reference must be positive")

    def component(value: int) -> float:
        return clamp100(100.0 * max(0, value) / reference)

    return {
        "security_findings": component(indicators.security_findings),
        "failed_security_checks": component(indicators.failed_security_checks),
        "auth_issues": component(indicators.auth_issues),
        "suspicious_code": component(indicators.suspicious_code),
        "task_failures": component(indicators.task_failures),
        "high_risk_tasks": component(indicators.high_risk_tasks),
    }


class RiskCalculator:
    """Combines normalized risk components into a single 0-100 score."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def score(self, indicators: RiskIndicators) -> float:
        """Compute the weighted risk score for a set of indicators."""
        components = normalized_indicator(indicators, self.config)
        (
            w_sec,
            w_failed,
            w_auth,
            w_susp,
            w_fail,
            w_high,
        ) = self.config.validated_weights()
        raw = (
            w_sec * components["security_findings"]
            + w_failed * components["failed_security_checks"]
            + w_auth * components["auth_issues"]
            + w_susp * components["suspicious_code"]
            + w_fail * components["task_failures"]
            + w_high * components["high_risk_tasks"]
        )
        return round(clamp100(raw), 2)

    def level(self, score: float) -> str:
        """Classify a risk score into NORMAL / ELEVATED / HIGH.

        Scores below ``elevated_threshold`` are NORMAL; scores below
        ``high_threshold`` are ELEVATED; everything else is HIGH.
        """
        clamped = clamp100(score)
        if clamped < self.config.elevated_threshold:
            return "NORMAL"
        if clamped < self.config.high_threshold:
            return "ELEVATED"
        return "HIGH"


__all__ = [
    "RiskCalculator",
    "RiskConfig",
    "RiskIndicators",
    "normalized_indicator",
]