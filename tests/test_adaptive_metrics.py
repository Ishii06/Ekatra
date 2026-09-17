"""Tests for adaptive metrics — workload and risk normalizers and scores."""

import pytest
from ekatra.orchestration.observer import RoleObservation, SystemObservation, observe
from ekatra.orchestration.workload import (
    WorkloadCalculator,
    WorkloadConfig,
    queue_length_score,
    complexity_score,
    delay_score,
    failure_rate_score,
)
from ekatra.orchestration.risk import (
    RiskCalculator,
    RiskConfig,
    RiskIndicators,
    normalized_indicator,
)
from ekatra.orchestration._scoring import clamp100
from ekatra.agents.base import Role


class TestClamp100:
    def test_below_zero(self):
        assert clamp100(-10) == 0.0

    def test_above_100(self):
        assert clamp100(150) == 100.0

    def test_midpoint(self):
        assert clamp100(50) == 50.0

    def test_zero(self):
        assert clamp100(0) == 0.0

    def test_100(self):
        assert clamp100(100) == 100.0


class TestWorkloadNormalizers:
    def test_queue_length_zero(self):
        assert queue_length_score(0, reference=10) == 0.0

    def test_queue_length_at_reference(self):
        assert queue_length_score(10, reference=10) == 100.0

    def test_queue_length_over_reference(self):
        assert queue_length_score(20, reference=10) == 100.0

    def test_complexity_min(self):
        assert complexity_score(1, complexity_max=5) == pytest.approx(20.0)

    def test_complexity_max(self):
        assert complexity_score(5, complexity_max=5) == 100.0

    def test_delay_zero(self):
        assert delay_score(0.0) == 0.0

    def test_delay_one(self):
        assert delay_score(1.0) == 100.0

    def test_failure_rate_zero(self):
        assert failure_rate_score(0.0) == 0.0

    def test_failure_rate_one(self):
        assert failure_rate_score(1.0) == 100.0


class TestWorkloadCalculator:
    def _obs(self, **kwargs):
        return RoleObservation(
            role=Role.BACKEND,
            queue_length=kwargs.get("queue_length", 0),
            avg_complexity=kwargs.get("avg_complexity", 1.0),
            delay_ratio=kwargs.get("delay_ratio", 0.0),
            failure_rate=kwargs.get("failure_rate", 0.0),
            total_agents=kwargs.get("total_agents", 1),
            active_agents=kwargs.get("active_agents", 0),
        )

    def test_score_zero_load(self):
        calc = WorkloadCalculator(WorkloadConfig())
        assert calc.score_for(self._obs(avg_complexity=0.0)) == 0.0

    def test_score_full_load(self):
        calc = WorkloadCalculator(WorkloadConfig())
        obs = self._obs(queue_length=20, avg_complexity=5.0, delay_ratio=1.0, failure_rate=1.0)
        score = calc.score_for(obs)
        assert score == pytest.approx(100.0, abs=0.01)

    def test_level_normal(self):
        calc = WorkloadCalculator(WorkloadConfig())
        assert calc.level(0.0) == "NORMAL"

    def test_level_elevated(self):
        calc = WorkloadCalculator(WorkloadConfig())
        assert calc.level(50.0) == "ELEVATED"

    def test_level_high(self):
        calc = WorkloadCalculator(WorkloadConfig())
        assert calc.level(80.0) == "HIGH"


class TestRiskNormalizers:
    def test_normalized_zero(self):
        cfg = RiskConfig()
        ind = RiskIndicators()
        result = normalized_indicator(ind, cfg)
        assert result["security_findings"] == 0.0

    def test_normalized_at_reference(self):
        cfg = RiskConfig()
        ind = RiskIndicators(security_findings=5)
        result = normalized_indicator(ind, cfg)
        assert result["security_findings"] == 50.0

    def test_normalized_above_reference(self):
        cfg = RiskConfig()
        ind = RiskIndicators(security_findings=10)
        result = normalized_indicator(ind, cfg)
        assert result["security_findings"] == 100.0


class TestRiskCalculator:
    def _indicators(self, **kwargs):
        return RiskIndicators(
            security_findings=kwargs.get("security_findings", 0),
            failed_security_checks=kwargs.get("failed_security_checks", 0),
            auth_issues=kwargs.get("auth_issues", 0),
            suspicious_code=kwargs.get("suspicious_code", 0),
            task_failures=kwargs.get("task_failures", 0),
            high_risk_tasks=kwargs.get("high_risk_tasks", 0),
        )

    def test_score_zero(self):
        calc = RiskCalculator(RiskConfig())
        assert calc.score(self._indicators()) == 0.0

    def test_score_full(self):
        calc = RiskCalculator(RiskConfig())
        ind = self._indicators(
            security_findings=10, failed_security_checks=10,
            auth_issues=10, suspicious_code=10,
            task_failures=10, high_risk_tasks=10,
        )
        assert calc.score(ind) == pytest.approx(100.0, abs=0.01)

    def test_level_normal(self):
        calc = RiskCalculator(RiskConfig())
        assert calc.level(0.0) == "NORMAL"

    def test_level_elevated(self):
        calc = RiskCalculator(RiskConfig())
        assert calc.level(50.0) == "ELEVATED"

    def test_level_high(self):
        calc = RiskCalculator(RiskConfig())
        assert calc.level(80.0) == "HIGH"


class TestObservation:
    def test_observe_empty(self):
        obs = observe([], [])
        total_queue = sum(r.queue_length for r in obs.roles.values())
        total_agents = sum(r.total_agents for r in obs.roles.values())
        assert total_queue == 0
        assert total_agents == 0

    def test_observe_with_tasks_and_agents(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 3, "assigned_agent": "BACKEND-1"},
            {"id": "T-2", "role": "frontend", "status": "PENDING", "priority": 2,
             "complexity": 2, "assigned_agent": None},
        ]
        agents = [
            {"agent_id": "BACKEND-1", "role": "backend", "status": "IDLE"},
            {"agent_id": "FRONTEND-1", "role": "frontend", "status": "ACTIVE"},
        ]
        obs = observe(tasks, agents)
        backend_obs = obs.role(Role.BACKEND)
        assert backend_obs.queue_length == 1
        assert backend_obs.total_agents == 1
        frontend_obs = obs.role(Role.FRONTEND)
        assert frontend_obs.queue_length == 1
        assert frontend_obs.total_agents == 1

    def test_role_observation_weighted_complexity(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 4, "assigned_agent": "BACKEND-1"},
            {"id": "T-2", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 2, "assigned_agent": "BACKEND-1"},
        ]
        agents = [{"agent_id": "BACKEND-1", "role": "backend", "status": "ACTIVE"}]
        obs = observe(tasks, agents)
        assert obs.role(Role.BACKEND).avg_complexity == 3.0

    def test_risk_indicators_derived(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "FAILED", "priority": 1,
             "complexity": 3, "assigned_agent": "BACKEND-1", "risk": 80},
        ]
        agents = [{"agent_id": "BACKEND-1", "role": "backend", "status": "COMPLETED"}]
        obs = observe(tasks, agents)
        assert obs.indicators.task_failures >= 1
        assert obs.indicators.high_risk_tasks == 1
