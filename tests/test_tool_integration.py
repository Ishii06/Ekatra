"""Integration tests for agent/tool execution (Milestone 6).

Covers agent↔tool wiring, explicit role permissions, structured failure
semantics, execution observability, the deterministic demo workflow, and
regression of the fixed baseline and adaptive workflows. No API key is
required for any of these tests.
"""

from __future__ import annotations

from collections import Counter

import pytest

from ekatra.agents.base import AgentStatus, Role
from ekatra.agents.roles import ROLES
from ekatra.config.settings import get_settings
from ekatra.graph import build_graph as build_fixed_graph
from ekatra.graph.adaptive import run_adaptive
from ekatra.graph.tools import (  # noqa: F401
    run_tools_demo,
    summarize,
)
from ekatra.state.state import EkatraState, create_initial_state
from ekatra.tasks import TaskManager
from ekatra.tools import ToolRegistry, role_policy_for
from ekatra.workspace import Workspace

PROJECT = "Build a simple todo application."


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    return Workspace(tmp_path / "proj")


@pytest.fixture
def ws_root(tmp_path) -> str:
    root = tmp_path / "ws"
    root.mkdir()
    return str(root)


def _agent(role: Role, workspace: Workspace, agent_id: str = "agent-t"):
    agent = ROLES[role](agent_id=agent_id)
    agent.strategy = "tools"
    agent.attach_workspace(workspace)
    return agent


def test_agent_use_tool_reads_file(workspace) -> None:
    workspace.write_text("notes.md", "hello")
    agent = _agent(Role.QA, workspace)
    result = agent.use_tool("read_file", task_id="T-1", path="notes.md")
    assert result.success is True
    assert result.agent_id == agent.agent_id
    assert result.task_id == "T-1"
    assert result.output["content"] == "hello"


def test_agent_unknown_tool_raises(workspace) -> None:
    agent = _agent(Role.QA, workspace)
    with pytest.raises(KeyError):
        agent.use_tool("no_such_tool", path="notes.md")


def test_agent_without_workspace_raises() -> None:
    agent = ROLES[Role.QA](agent_id="qa-n")
    with pytest.raises(RuntimeError):
        agent.use_tool("read_file", path="notes.md")


def test_use_tool_records_observability(workspace) -> None:
    workspace.write_text("a.txt", "x")
    agent = _agent(Role.QA, workspace)
    assert agent.tool_calls == []
    agent.use_tool("read_file", task_id="T-7", path="a.txt")
    assert len(agent.tool_calls) == 1
    assert agent.metadata["tool_calls"] == 1
    record = agent.tool_calls[0].to_dict()
    assert record["agent_id"] == agent.agent_id
    assert record["task_id"] == "T-7"
    assert record["success"] is True
    assert record["timestamp"]
    assert record["duration_ms"] >= 0


def test_pm_cannot_write(workspace) -> None:
    agent = _agent(Role.PROJECT_MANAGER, workspace)
    with pytest.raises(PermissionError):
        agent.use_tool("write_file", path="docs/evil.md", content="x")
    assert agent.tool_calls == []


def test_pm_can_inspect(workspace) -> None:
    agent = _agent(Role.PROJECT_MANAGER, workspace)
    result = agent.use_tool("inspect_path", path=".")
    assert result.success is True


def test_architect_can_write_docs_only(workspace) -> None:
    agent = _agent(Role.ARCHITECT, workspace)
    ok = agent.use_tool("write_file", path="docs/architecture.md", content="# Arch\n")
    assert ok.success is True
    with pytest.raises(PermissionError):
        agent.use_tool("write_file", path="backend/main.py", content="x")


def test_backend_can_write_backend_only(workspace) -> None:
    agent = _agent(Role.BACKEND, workspace)
    ok = agent.use_tool("write_file", path="backend/main.py", content="x")
    assert ok.success is True
    with pytest.raises(PermissionError):
        agent.use_tool("write_file", path="docs/report.md", content="x")


def test_frontend_can_write_frontend_only(workspace) -> None:
    agent = _agent(Role.FRONTEND, workspace)
    ok = agent.use_tool("write_file", path="frontend/app.py", content="x")
    assert ok.success is True
    with pytest.raises(PermissionError):
        agent.use_tool("write_file", path="docs/report.md", content="x")


def test_qa_and_security_can_write_docs_only(workspace) -> None:
    for role in (Role.QA, Role.SECURITY):
        agent = _agent(role, workspace)
        ok = agent.use_tool("write_file", path="docs/report.md", content="x")
        assert ok.success is True
        with pytest.raises(PermissionError):
            agent.use_tool("write_file", path="backend/main.py", content="x")


def test_missing_file_tool_use_returns_failure_result(workspace) -> None:
    agent = _agent(Role.QA, workspace)
    result = agent.use_tool("read_file", task_id="T-2", path="missing.txt")
    assert result.success is False
    assert result.error is not None
    assert len(agent.tool_calls) == 1


def test_policy_denied_build_causes_task_failure(workspace) -> None:
    from ekatra.tools import RoleToolPolicy

    manager = TaskManager()
    task = manager.create(
        role=Role.BACKEND,
        description="Backend implementation",
        priority=3,
        complexity=4,
        risk=25,
        dependencies=[],
    )

    agent = ROLES[Role.BACKEND](agent_id="backend-denied")
    agent.strategy = "tools"
    agent.attach_workspace(
        workspace,
        policy=RoleToolPolicy(
            role=Role.BACKEND,
            allowed_tools={"read_file"},
            write_prefixes=(),
        ),
    )
    result = agent.execute(task)
    assert result.success is False
    assert "Execution failed" in result.output
    assert agent.status == AgentStatus.IDLE


def test_task_execution_success_with_tools(workspace) -> None:
    manager = TaskManager()
    task = manager.create(
        role=Role.ARCHITECT,
        description="Architecture",
        priority=3,
        complexity=3,
        risk=10,
        dependencies=[],
    )
    agent = _agent(Role.ARCHITECT, workspace)
    result = agent.execute(task)
    assert result.success is True
    assert agent.status == AgentStatus.COMPLETED
    assert (workspace.root / "docs" / "architecture.md").is_file()


def test_role_policy_is_explicit() -> None:
    pm = role_policy_for(Role.PROJECT_MANAGER)
    assert pm.allows("read_file")
    assert pm.allows("list_dir")
    assert not pm.allows("write_file")

    architect = role_policy_for(Role.ARCHITECT)
    assert architect.allows("write_file", path="docs/architecture.md")
    assert not architect.allows("write_file", path="backend/main.py")

    backend = role_policy_for(Role.BACKEND.value)
    assert backend.allows("write_file", path="backend/main.py")
    assert not backend.allows("write_file", path="docs/architecture.md")


def test_no_api_key_required(ws_root) -> None:
    assert get_settings().has_api_key() is False
    result = run_tools_demo(PROJECT, ws_root)
    assert result["current_step"] == "security"


def test_demo_workflow_end_to_end(ws_root) -> None:
    result = run_tools_demo(PROJECT, ws_root)

    assert result["current_step"] == "security"
    assert len(result["tasks"]) == 5
    assert sum(1 for t in result["tasks"] if t["status"] == "COMPLETED") == 5
    assert len(result["agents"]) == 6

    ws = Workspace(ws_root)
    assert (ws.root / "docs" / "architecture.md").is_file()
    assert (ws.root / "backend" / "main.py").is_file()
    assert (ws.root / "frontend" / "app.py").is_file()
    assert (ws.root / "docs" / "qa_report.md").is_file()
    assert (ws.root / "docs" / "security_report.md").is_file()


def test_demo_artifacts_content(ws_root) -> None:
    run_tools_demo(PROJECT, ws_root)
    ws = Workspace(ws_root)
    assert "# Architecture" in ws.read_text("docs/architecture.md")
    assert "def handle_request" in ws.read_text("backend/main.py")
    assert "def render_page" in ws.read_text("frontend/app.py")
    assert "All checks passed." in ws.read_text("docs/qa_report.md")
    assert "No critical vulnerabilities found." in ws.read_text("docs/security_report.md")


def test_demo_execution_observability(ws_root) -> None:
    result = run_tools_demo(PROJECT, ws_root)
    calls = result["tool_calls"]
    assert len(calls) == 13
    assert all(c["success"] for c in calls)
    assert all(c["timestamp"] for c in calls)
    assert all(c["duration_ms"] >= 0 for c in calls)
    assert all(c["agent_id"] for c in calls)
    assert all(c["task_id"] for c in calls)

    role_by_agent = {a["agent_id"]: a["role"] for a in result["agents"]}
    counts = Counter(role_by_agent[c["agent_id"]] for c in calls)
    assert counts == {
        "project_manager": 2,
        "architect": 2,
        "backend": 1,
        "frontend": 1,
        "qa": 3,
        "security": 4,
    }

    by_tool = Counter(c["tool_name"] for c in calls)
    assert by_tool == {
        "write_file": 5,
        "read_file": 4,
        "list_dir": 2,
        "inspect_path": 2,
    }

    pm_calls = [c for c in calls if c["tool_name"] == "write_file"]
    assert all(role_by_agent[c["agent_id"]] != "project_manager" for c in pm_calls)


def test_demo_summary(ws_root) -> None:
    result = run_tools_demo(PROJECT, ws_root)
    summary = summarize(result)
    assert summary["tasks"] == 5
    assert summary["tasks_completed"] == 5
    assert summary["tool_calls"] == 13
    assert summary["tool_calls_ok"] == 13
    assert summary["tool_calls_failed"] == 0


def test_regression_fixed_workflow() -> None:
    result = build_fixed_graph().invoke(create_initial_state(PROJECT))
    assert result["current_step"] == "security"
    assert len(result["messages"]) == 6
    assert result["adaptive_decisions"] == []
    assert len(result["tasks"]) == 5
    assert len(result["agents"]) == 6
    assert result["tool_calls"] == []
    assert set(result.keys()) == EkatraState.__annotations__.keys()


def test_regression_adaptive_workflow() -> None:
    result = run_adaptive(PROJECT)
    assert result["current_step"] in {"adaptive_adapt", "adaptive_execute"}
    assert result["adaptive_decisions"]
    assert sum(1 for t in result["tasks"] if t["status"] == "COMPLETED") == 5
    assert result["tool_calls"] == []