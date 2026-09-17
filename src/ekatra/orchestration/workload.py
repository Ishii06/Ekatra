"""Deterministic workload model.

Implements the documented experimental workload formula
(``docs/04-adaptive-orchestration.md``):

    W = 0.40 x queue length + 0.30 x task complexity
      + 0.20 x execution delay + 0.10 x failure rate

All component inputs are normalized to a 0-100 scale and the weighted result
is clamped to 0-100. Weights, the normalization references, and the level
thresholds are configurable experimental parameters, not validated constants.

Normalization assumptions (documented, deterministic):

* queue length: ``100 * queue / queue_reference`` (a saturated queue of
  ``queue_reference`` tasks yields a full queue component)
* complexity: ``100 * avg_complexity / complexity_max`` (complexity is the
  documented 1-5 scale)
* execution delay: the observed delay ratio (0-1), scaled by 100
* failure rate: the observed failure ratio (0-1), scaled by 100

Every component is clamped to [0, 100].
"""

from __future__ import annotations

from pydantic import BaseModel

from ekatra.orchestration._scoring import clamp100
from ekatra.orchestration.observer import RoleObservation


def _clamp100(value: float) -> float:
    return max(0.0, min(100.0, value))


def queue_length_score(queue_length: int, reference: int) -> float:
    """Normalize a queue length to 0-100 against a saturated-queue reference."""
    if reference <= 0:
        raise ValueError("queue reference must be positive")
    return clamp100(100.0 * max(0, queue_length) / reference)


def complexity_score(avg_complexity: float, complexity_max: int) -> float:
    """Normalize an average complexity (1-5 scale) to 0-100."""
    if complexity_max <= 0:
        raise ValueError("complexity maximum must be positive")
    return clamp100(100.0 * avg_complexity / complexity_max)


def delay_score(delay_ratio: float) -> float:
    """Normalize an execution-delay ratio (0-1) to 0-100."""
    return clamp100(100.0 * delay_ratio)


def failure_rate_score(failure_rate: float) -> float:
    """Normalize a failure rate (0-1) to 0-100."""
    return clamp100(100.0 * failure_rate)


class WorkloadConfig(BaseModel):
    """Configuration for the experimental workload model.

    Attributes:
        weight_queue: Weight of the queue-length component (default 0.40).
        weight_complexity: Weight of the complexity component (default 0.30).
        weight_delay: Weight of the execution-delay component (default 0.20).
        weight_failure: Weight of the failure-rate component (default 0.10).
        queue_reference: Saturated queue length for normalization (default 10).
        complexity_max: Maximum representable complexity (default 5).
        continue_below: Scores below this are treated as a normal workload.
        monitor_below: Scores below this (and at/above continue_below) are
            treated as an elevated workload that should be monitored.
    """

    weight_queue: float = 0.40
    weight_complexity: float = 0.30
    weight_delay: float = 0.20
    weight_failure: float = 0.10
    queue_reference: int = 10
    complexity_max: int = 5
    continue_below: float = 40.0
    monitor_below: float = 70.0

    def validated_weights(self) -> tuple[float, float, float, float]:
        """Return the four weights after clamping each to [0, 1]."""
        weights = (
            max(0.0, min(1.0, self.weight_queue)),
            max(0.0, min(1.0, self.weight_complexity)),
            max(0.0, min(1.0, self.weight_delay)),
            max(0.0, min(1.0, self.weight_failure)),
        )
        return weights


class WorkloadCalculator:
    """Combines normalized workload components into a single 0-100 score."""

    def __init__(self, config: WorkloadConfig | None = None) -> None:
        self.config = config or WorkloadConfig()

    # -- component normalization -------------------------------------------

    def queue_score(self, queue_length: int) -> float:
        return queue_length_score(queue_length, self.config.queue_reference)

    def complexity_score(self, avg_complexity: float) -> float:
        return complexity_score(avg_complexity, self.config.complexity_max)

    def delay_score(self, delay_ratio: float) -> float:
        return delay_score(delay_ratio)

    def failure_rate_score(self, failure_rate: float) -> float:
        return failure_rate_score(failure_rate)

    # -- combination -------------------------------------------------------

    def score(
        self,
        queue_score_: float,
        complexity_score_: float,
        delay_score_: float,
        failure_score: float,
    ) -> float:
        """Weighted combination of four component scores (each 0-100).

        Raises:
            ValueError: When a component score is not within [0, 100].
        """
        components = (queue_score_, complexity_score_, delay_score_, failure_score)
        for value in components:
            if value < 0.0 or value > 100.0:
                raise ValueError(f"component score out of range: {value}")
        wq, wc, wd, wf = self.config.validated_weights()
        raw = wq * queue_score_ + wc * complexity_score_ + wd * delay_score_ + wf * failure_score
        return round(clamp100(raw), 2)

    def score_for(self, observation: RoleObservation) -> float:
        """Compute the workload score directly from a role observation."""
        return self.score(
            self.queue_score(observation.queue_length),
            self.complexity_score(observation.avg_complexity),
            self.delay_score(observation.delay_ratio),
            self.failure_rate_score(observation.failure_rate),
        )

    # -- level interpretation ----------------------------------------------

    def level(self, score: float) -> str:
        """Classify a workload score into NORMAL / ELEVATED / HIGH.

        Scores below ``continue_below`` are NORMAL; scores below
        ``monitor_below`` are ELEVATED; everything else is HIGH.
        """
        clamped = clamp100(score)
        if clamped < self.config.continue_below:
            return "NORMAL"
        if clamped < self.config.monitor_below:
            return "ELEVATED"
        return "HIGH"


__all__ = [
    "WorkloadCalculator",
    "WorkloadConfig",
    "complexity_score",
    "delay_score",
    "failure_rate_score",
    "queue_length_score",
]