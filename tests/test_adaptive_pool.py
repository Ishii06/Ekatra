"""Tests for adaptive agent pool — spawn, terminate, baseline protection."""

import pytest
from ekatra.agents.base import AgentStatus, Role
from ekatra.orchestration.pool import AdaptiveAgentPool, SPAWNABLE_ROLES, _is_baseline, _BASELINE_IDS


class TestAdaptiveAgentPool:
    def test_baseline_created(self):
        pool = AdaptiveAgentPool()
        ids = pool.agent_ids()
        assert ids == [
            "PM-1", "ARCH-1", "BACKEND-1", "FRONTEND-1", "QA-1", "SECURITY-1"
        ]

    def test_baseline_agents_are_idle(self):
        pool = AdaptiveAgentPool()
        for agent in pool.list_agents():
            assert agent.status is AgentStatus.IDLE

    def test_spawn_increases_count(self):
        pool = AdaptiveAgentPool()
        initial = len(pool)
        pool.spawn(Role.BACKEND)
        assert len(pool) == initial + 1

    def test_spawn_assigns_correct_role(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.BACKEND)
        assert agent.role is Role.BACKEND
        assert agent.status is AgentStatus.IDLE

    def test_spawn_assigns_unique_id(self):
        pool = AdaptiveAgentPool()
        a1 = pool.spawn(Role.BACKEND)
        a2 = pool.spawn(Role.BACKEND)
        assert a1.agent_id != a2.agent_id
        assert a1.agent_id == "BACKEND-2"
        assert a2.agent_id == "BACKEND-3"

    def test_spawn_only_spawnable_roles(self):
        pool = AdaptiveAgentPool()
        with pytest.raises(ValueError, match="not spawnable"):
            pool.spawn(Role.PROJECT_MANAGER)

    def test_terminate_spawned_agent(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.BACKEND)
        pool.terminate(agent.agent_id)
        # Terminated agent should not appear in list_agents
        ids = pool.agent_ids()
        assert agent.agent_id not in ids

    def test_terminate_baseline_rejected(self):
        pool = AdaptiveAgentPool()
        with pytest.raises(ValueError, match="baseline"):
            pool.terminate("BACKEND-1")

    def test_terminate_active_rejected(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.BACKEND)
        agent.status = AgentStatus.ACTIVE
        with pytest.raises(ValueError, match="active"):
            pool.terminate(agent.agent_id)

    def test_baseline_protection(self):
        pool = AdaptiveAgentPool()
        for agent_id in _BASELINE_IDS.values():
            assert _is_baseline(agent_id)
        assert not _is_baseline("BACKEND-2")

    def test_list_agents_excludes_terminated(self):
        pool = AdaptiveAgentPool()
        agent = pool.spawn(Role.QA)
        pool.terminate(agent.agent_id)
        ids = pool.agent_ids()
        assert agent.agent_id not in ids

    def test_available_for(self):
        pool = AdaptiveAgentPool()
        idle = pool.available_for(Role.BACKEND)
        assert len(idle) == 1
        assert idle[0].agent_id == "BACKEND-1"

    def test_get_by_role(self):
        pool = AdaptiveAgentPool()
        agent = pool.get_by_role(Role.FRONTEND)
        assert agent.agent_id == "FRONTEND-1"

    def test_agent_counts(self):
        pool = AdaptiveAgentPool()
        pool.spawn(Role.BACKEND)
        counts = pool.agent_counts()
        assert counts[Role.BACKEND]["total"] == 2
        assert counts[Role.BACKEND]["idle_spawned"] == 1
        assert counts[Role.FRONTEND]["total"] == 1

    def test_to_dicts_from_dicts_roundtrip(self):
        pool = AdaptiveAgentPool()
        pool.spawn(Role.BACKEND)
        dicts = pool.to_dicts()
        pool2 = AdaptiveAgentPool.from_dicts(dicts)
        assert pool2.agent_ids() == pool.agent_ids()

    def test_multiple_role_spawn(self):
        pool = AdaptiveAgentPool()
        pool.spawn(Role.BACKEND)
        pool.spawn(Role.FRONTEND)
        pool.spawn(Role.QA)
        pool.spawn(Role.SECURITY)
        assert len(pool) == 10  # 6 baseline + 4 spawned
