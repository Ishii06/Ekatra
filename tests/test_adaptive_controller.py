"""Tests for adaptive controller — observer, decisions, controller, reassign, prioritization."""

import pytest
from datetime import datetime, timezone

from ekatra.agents.base import Role
from ekatra.orchestration.observer import RoleObservation, SystemObservation, observe
from ekatra.orchestration.decisions import AdaptiveAction, AdaptiveDecision
from ekatra.orchestration.controller import AdaptiveController, ControllerConfig
from ekatra.orchestration.workload import WorkloadConfig
from ekatra.orchestration.risk import RiskConfig


def _fixed_ts():
    return "2026-01-01T00:00:00+00:00"


def _controller(**kwargs):
    cfg = ControllerConfig(
        workload=kwargs.get("workload", WorkloadConfig()),
        risk=kwargs.get("risk", RiskConfig()),
        max_agents_per_role=kwargs.get("max_agents_per_role", 4),
        now=_fixed_ts,
    )
    return AdaptiveController(cfg)


def _empty_obs():
    return observe([], [])


def _make_decision(action, **kw):
    return AdaptiveDecision(
        timestamp=_fixed_ts(),
        cycle=kw.get("cycle", 1),
        decision=action,
        workload_score=kw.get("workload_score", 0.0),
        risk_score=kw.get("risk_score", 0.0),
        workload_level=kw.get("workload_level", "NORMAL"),
        risk_level=kw.get("risk_level", "NORMAL"),
        reason=kw.get("reason", "test"),
        affected_role=kw.get("affected_role"),
        affected_agent=kw.get("affected_agent"),
        affected_task=kw.get("affected_task"),
        previous_state=kw.get("previous_state", {}),
        resulting_state=kw.get("resulting_state", {}),
    )


class TestAdaptiveDecision:
    def test_continue_is_valid(self):
        d = _make_decision(AdaptiveAction.CONTINUE)
        assert d.decision is AdaptiveAction.CONTINUE
        assert d.previous_state == {}

    def test_spawn_requires_role(self):
        with pytest.raises(Exception):
            AdaptiveDecision(
                timestamp=_fixed_ts(), cycle=1,
                decision=AdaptiveAction.SPAWN,
                workload_score=0, risk_score=0,
                workload_level="NORMAL", risk_level="NORMAL",
                reason="test", previous_state={}, resulting_state={},
            )

    def test_terminate_requires_agent(self):
        with pytest.raises(Exception):
            AdaptiveDecision(
                timestamp=_fixed_ts(), cycle=1,
                decision=AdaptiveAction.TERMINATE,
                workload_score=0, risk_score=0,
                workload_level="NORMAL", risk_level="NORMAL",
                reason="test", previous_state={}, resulting_state={},
            )

    def test_to_dict_roundtrip(self):
        d = _make_decision(AdaptiveAction.SPAWN, affected_role="backend")
        data = d.to_dict()
        assert data["decision"] == "SPAWN"
        assert data["affected_role"] == "backend"


class TestAdaptiveController:
    def test_continue_when_idle(self):
        ctrl = _controller()
        obs = observe([], [])
        d = ctrl.evaluate(obs)
        assert d.decision is AdaptiveAction.CONTINUE

    def test_spawn_when_high_workload(self):
        tasks = [
            {"id": f"T-{i}", "role": "backend", "status": "FAILED", "priority": 1,
             "complexity": 5, "assigned_agent": "BACKEND-1"}
            for i in range(15)
        ]
        agents = [{"agent_id": "BACKEND-1", "role": "backend", "status": "ACTIVE"}]
        obs = observe(tasks, agents)
        ac = {Role.BACKEND: {"total": 1, "idle": 0, "idle_spawned": 0}}
        ctrl = _controller()
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision is AdaptiveAction.SPAWN
        assert d.affected_role == "backend"

    def test_spawn_security_when_risk_high(self):
        tasks = [
            {"id": f"SEC-{i}", "role": "security", "status": "FAILED", "priority": 1,
             "complexity": 3, "assigned_agent": "SECURITY-1", "risk": 90,
             "description": "vulnerability finding in auth module"}
            for i in range(10)
        ] + [
            {"id": f"FAIL-{i}", "role": "backend", "status": "FAILED", "priority": 1,
             "complexity": 3, "assigned_agent": "BACKEND-1", "risk": 90,
             "description": "suspicious code injection detected"}
            for i in range(5)
        ] + [
            {"id": f"FAIL2-{i}", "role": "frontend", "status": "FAILED", "priority": 1,
             "complexity": 3, "assigned_agent": "FRONTEND-1", "risk": 90,
             "description": "auth permission error"}
            for i in range(5)
        ]
        agents = [
            {"agent_id": "SECURITY-1", "role": "security", "status": "COMPLETED"},
            {"agent_id": "BACKEND-1", "role": "backend", "status": "COMPLETED"},
            {"agent_id": "FRONTEND-1", "role": "frontend", "status": "COMPLETED"},
        ]
        obs = observe(tasks, agents)
        ac = {Role.SECURITY: {"total": 1, "idle": 0, "idle_spawned": 0}}
        ctrl = _controller()
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision is AdaptiveAction.SPAWN
        assert d.affected_role == "security"

    def test_terminate_idle_spawned(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 1, "assigned_agent": "BACKEND-1"},
        ]
        agents = [
            {"agent_id": "BACKEND-1", "role": "backend", "status": "ACTIVE"},
            {"agent_id": "BACKEND-2", "role": "backend", "status": "IDLE"},
        ]
        obs = observe(tasks, agents)
        ac = {Role.BACKEND: {"total": 2, "idle": 1, "idle_spawned": 1}}
        ctrl = _controller()
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision in (AdaptiveAction.TERMINATE, AdaptiveAction.CONTINUE, AdaptiveAction.PRIORITIZE, AdaptiveAction.REASSIGN)

    def test_reassign_when_idle_sibling(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 3, "assigned_agent": "BACKEND-1"},
            {"id": "T-2", "role": "backend", "status": "PENDING", "priority": 1,
             "complexity": 3, "assigned_agent": None},
        ]
        agents = [
            {"agent_id": "BACKEND-1", "role": "backend", "status": "ACTIVE"},
            {"agent_id": "BACKEND-2", "role": "backend", "status": "IDLE"},
        ]
        obs = observe(tasks, agents)
        ac = {Role.BACKEND: {"total": 2, "idle": 1, "idle_spawned": 0}}
        ctrl = _controller()
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision in (AdaptiveAction.REASSIGN, AdaptiveAction.CONTINUE)

    def test_prioritize_high_risk(self):
        tasks = [
            {"id": "T-1", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 3, "assigned_agent": "BACKEND-1", "risk": 90},
        ]
        agents = [
            {"agent_id": "BACKEND-1", "role": "backend", "status": "ACTIVE"},
        ]
        obs = observe(tasks, agents)
        ac = {Role.BACKEND: {"total": 1, "idle": 0, "idle_spawned": 0}}
        risk_cfg = RiskConfig(high_risk_task_threshold=50)
        ctrl = _controller(risk=risk_cfg)
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision in (AdaptiveAction.PRIORITIZE, AdaptiveAction.CONTINUE)

    def test_no_spawn_above_cap(self):
        tasks = [
            {"id": f"T-{i}", "role": "backend", "status": "ASSIGNED", "priority": 1,
             "complexity": 5, "assigned_agent": f"BACKEND-{(i % 4) + 1}"}
            for i in range(15)
        ]
        agents = [
            {"agent_id": f"BACKEND-{i}", "role": "backend", "status": "ACTIVE"}
            for i in range(1, 5)
        ]
        obs = observe(tasks, agents)
        ac = {Role.BACKEND: {"total": 4, "idle": 0, "idle_spawned": 0}}
        ctrl = _controller(max_agents_per_role=4)
        d = ctrl.evaluate(obs, agent_counts=ac, all_agents=agents, tasks=tasks)
        assert d.decision is not AdaptiveAction.SPAWN


class TestReassignTask:
    def test_reassign_updates_assignment(self):
        from ekatra.tasks.manager import TaskManager
        from ekatra.orchestration.adaptations import reassign_task
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test")
        mgr.assign(t.id, "BACKEND-1")
        reassign_task(mgr, t.id, "BACKEND-2")
        assert mgr.get(t.id).assigned_agent == "BACKEND-2"

    def test_reassign_same_agent_noop(self):
        from ekatra.tasks.manager import TaskManager
        from ekatra.orchestration.adaptations import reassign_task
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test")
        mgr.assign(t.id, "BACKEND-1")
        reassign_task(mgr, t.id, "BACKEND-1")
        assert mgr.get(t.id).assigned_agent == "BACKEND-1"
