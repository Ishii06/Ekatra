"""Integration tests for the adaptive workflow."""

import pytest
from ekatra.agents.base import AgentStatus, Role
from ekatra.orchestration.pool import AdaptiveAgentPool
from ekatra.orchestration.adaptations import apply_decision
from ekatra.orchestration.decisions import AdaptiveAction, AdaptiveDecision
from ekatra.tasks.manager import TaskManager
from ekatra.tasks.task import Task


def _fixed_ts():
    return "2026-01-01T00:00:00+00:00"


def _decision(action, **kw):
    return AdaptiveDecision(
        timestamp=_fixed_ts(),
        cycle=kw.get("cycle", 1),
        decision=action,
        workload_score=kw.get("workload_score", 0.0),
        risk_score=kw.get("risk_score", 0.0),
        workload_level=kw.get("workload_level", "LOW"),
        risk_level=kw.get("risk_level", "LOW"),
        reason=kw.get("reason", "test"),
        affected_role=kw.get("affected_role"),
        affected_agent=kw.get("affected_agent"),
        affected_task=kw.get("affected_task"),
        previous_state=kw.get("previous_state", {}),
        resulting_state=kw.get("resulting_state", {}),
    )


# ---- apply_decision integration ----

class TestApplyDecision:
    def test_spawn_enriches_decision(self):
        pool = AdaptiveAgentPool()
        mgr = TaskManager()
        d = _decision(AdaptiveAction.SPAWN, affected_role="backend")
        result = apply_decision(d, pool, mgr)
        assert result.affected_agent is not None
        assert result.affected_agent.startswith("BACKEND-")
        assert "spawned_agent" in result.resulting_state

    def test_terminate_enriches_decision(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.BACKEND)
        mgr = TaskManager()
        d = _decision(AdaptiveAction.TERMINATE, affected_agent=agent.agent_id)
        result = apply_decision(d, pool, mgr)
        assert "terminated_agent" in result.resulting_state

    def test_prioritize_enriches_decision(self):
        pool = AdaptiveAgentPool()
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test", priority=1)
        mgr.assign(t.id, "BACKEND-1")
        d = _decision(AdaptiveAction.PRIORITIZE, affected_task=t.id,
                       resulting_state={"priority": 3}, reason="risk high")
        result = apply_decision(d, pool, mgr)
        assert mgr.get(t.id).priority == 3
        assert len(mgr.get(t.id).priority_history) == 1

    def test_reassign_enriches_decision(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.BACKEND)
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test")
        mgr.assign(t.id, "BACKEND-1")
        d = _decision(AdaptiveAction.REASSIGN, affected_task=t.id,
                       affected_agent=agent.agent_id)
        result = apply_decision(d, pool, mgr)
        assert mgr.get(t.id).assigned_agent == agent.agent_id

    def test_continue_noop(self):
        pool = AdaptiveAgentPool()
        mgr = TaskManager()
        d = _decision(AdaptiveAction.CONTINUE)
        result = apply_decision(d, pool, mgr)
        assert result.resulting_state == {"action": "none"}


# ---- Task priority_history ----

class TestTaskPriorityHistory:
    def test_priority_change_recorded(self):
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test", priority=1)
        mgr.set_priority(t.id, 2, reason="high risk")
        task = mgr.get(t.id)
        assert task.priority == 2
        assert len(task.priority_history) == 1
        assert task.priority_history[0]["previous_priority"] == 1
        assert task.priority_history[0]["priority"] == 2

    def test_priority_same_noop(self):
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test", priority=2)
        mgr.set_priority(t.id, 2, reason="same")
        assert len(mgr.get(t.id).priority_history) == 0

    def test_priority_invalid_raises(self):
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test")
        with pytest.raises(ValueError):
            mgr.set_priority(t.id, 5)

    def test_multiple_changes(self):
        mgr = TaskManager()
        t = mgr.create(role="backend", description="test", priority=1)
        mgr.set_priority(t.id, 2, reason="first")
        mgr.set_priority(t.id, 3, reason="second")
        task = mgr.get(t.id)
        assert task.priority == 3
        assert len(task.priority_history) == 2


# ---- Fixed workflow unchanged ----

class TestFixedWorkflowUnchanged:
    def test_fixed_graph_builds(self):
        from ekatra.graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_fixed_workflow_executes(self):
        from ekatra.graph import run
        result = run({"project_description": "test app"})
        assert result["current_step"] == "security"
        assert len(result["messages"]) == 6
        assert result["adaptive_decisions"] == []

    def test_adaptive_decisions_empty_in_fixed(self):
        from ekatra.graph import run
        result = run({"project_description": "test"})
        assert result["adaptive_decisions"] == []


# ---- Adaptive workflow graph ----

class TestAdaptiveGraph:
    def test_adaptive_graph_builds(self):
        from ekatra.graph.adaptive import build_adaptive_graph
        graph = build_adaptive_graph()
        assert graph is not None

    def test_adaptive_initial_state(self):
        from ekatra.graph.adaptive import create_adaptive_initial_state
        s = create_adaptive_initial_state("test app")
        assert s["adaptive_cycle"] == 1
        assert s["project_description"] == "test app"

    def test_adaptive_workflow_executes(self):
        from ekatra.graph.adaptive import run_adaptive
        result = run_adaptive("test app")
        assert result["adaptive_cycle"] >= 1
        assert len(result["adaptive_decisions"]) >= 1
        assert len(result["messages"]) >= 1

    def test_adaptive_workflow_completes_all_tasks(self):
        from ekatra.graph.adaptive import run_adaptive
        result = run_adaptive("test app")
        tasks = result.get("tasks", [])
        assert len(tasks) > 0
        assert all(t["status"] == "COMPLETED" for t in tasks)

    def test_adaptive_workflow_has_metrics(self):
        from ekatra.graph.adaptive import run_adaptive
        result = run_adaptive("test app")
        metrics = result.get("metrics", {})
        assert "adaptive_cycle" in metrics
        assert "strategy" in metrics
        assert metrics["strategy"] == "adaptive"

    def test_adaptive_workflow_no_api_key(self):
        import os
        os.environ.pop("GEMINI_API_KEY", None)
        from ekatra.graph.adaptive import run_adaptive
        result = run_adaptive("test app")
        assert len(result["adaptive_decisions"]) >= 1
