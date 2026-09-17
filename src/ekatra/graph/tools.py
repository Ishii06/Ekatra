"""Deterministic tool-assisted demo workflow for Ekatra.

Demonstrates Milestone 6 execution and tool integration without any LLM:

    PM plans → Architect artifact → Backend artifact → Frontend artifact
           → QA inspects → Security inspects

Unlike the fixed baseline (``graph/nodes.py``), role agents execute their tasks
through workspace-bounded tools (``ekatra.tools``) instead of mock output. Every
tool execution is recorded in the accumulated state field ``tool_calls`` for
observability, and each role is restricted by its explicit permission policy
(see ``ekatra.tools.registry``).

The workflow never touches the real project source tree: ``run_tools_demo``
requires an explicit ``workspace_root`` inside which all artifacts are created.
"""

from __future__ import annotations

import json
import tempfile

from ekatra.agents import FixedAgentPool, Role
from ekatra.graph.nodes import _RESULT_RECIPIENTS
from ekatra.observability.integration import (
    task_assigned_event,
    task_completed_event,
    task_created_event,
    task_started_event,
    tool_executed_event,
    workflow_started_event,
    with_workflow_completed,
)
from ekatra.orchestration import MessageBus, MessageType
from ekatra.state.state import EkatraState, create_initial_state
from ekatra.tasks import TaskManager
from ekatra.workspace import Workspace

EXECUTION_ROLES = (
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

EXAMPLE = "Build a simple todo application."


def _compute_metrics(tasks: list[dict], agents: list[dict], tool_count: int) -> dict:
    return {
        "strategy": "tools",
        "tasks_created": len(tasks),
        "tasks_completed": sum(1 for t in tasks if t["status"] == "COMPLETED"),
        "agents": len(agents),
        "tools_executed": tool_count,
    }


def _build_bus(state: EkatraState, pool: FixedAgentPool) -> MessageBus:
    bus = MessageBus.from_dicts(state.get("communication", []))
    for agent in pool.list_agents():
        agent.attach_bus(bus)
    return bus


def _attach_tools(pool: FixedAgentPool, workspace: Workspace) -> None:
    """Switch every agent to tool-assisted execution on the given workspace."""
    for agent in pool.list_agents():
        agent.strategy = "tools"
        agent.attach_workspace(workspace)


def _require_workspace(state: EkatraState) -> Workspace:
    root = state.get("workspace_root")
    if not root:
        raise ValueError(
            "The tool-assisted demo workflow requires a state['workspace_root']."
        )
    return Workspace(root)


def demo_plan(state: EkatraState) -> dict:
    """PM plans the fixed task set, then inspects the workspace via tools."""
    description = state.get("project_description", "")
    workspace = _require_workspace(state)

    pool = FixedAgentPool()
    manager = TaskManager()
    _attach_tools(pool, workspace)

    pm = pool.get_by_role(Role.PROJECT_MANAGER)
    result = pm.plan(description)
    pm.use_tool("inspect_path", task_id="PLAN", path=".")
    pm.use_tool("list_dir", task_id="PLAN", path=".")
    tool_records = [r.to_dict() for r in pm.tool_calls]

    bus = _build_bus(state, pool)
    pm.broadcast(
        MessageType.STATUS_UPDATE,
        f"Planning complete for {description!r}: {len(result.data)} tasks created.",
    )

    id_by_role: dict[Role, str] = {}
    for task_def in result.data:
        dependencies = [id_by_role[dep] for dep in task_def["dependencies"]]
        task = manager.create(
            role=task_def["role"],
            description=task_def["description"],
            priority=task_def["priority"],
            complexity=task_def["complexity"],
            risk=task_def["risk"],
            dependencies=dependencies,
        )
        id_by_role[task.role] = task.id

        agent = pool.get_by_role(task.role)
        manager.assign(task.id, agent.agent_id)
        agent.receive_task(task.id)
        agent.metadata["assigned_task_id"] = task.id
        pm.send(
            MessageType.TASK_ASSIGNMENT,
            f"Assigned {task.id} ({task.role.value}) to you: {task.description}",
            related_task_id=task.id,
            recipient=agent.agent_id,
        )

    tasks = manager.to_dicts()
    agents = pool.to_dicts()
    observability_events = [workflow_started_event(description)]
    observability_events.extend(tool_executed_event(r) for r in tool_records)
    observability_events.extend(task_created_event(t) for t in tasks)
    observability_events.extend(task_assigned_event(t) for t in tasks)
    return {
        "current_step": Role.PROJECT_MANAGER.value,
        "tasks": tasks,
        "agents": agents,
        "messages": result.messages,
        "communication": bus.to_dicts(),
        "metrics": _compute_metrics(tasks, agents, len(tool_records)),
        "tool_calls": tool_records,
        "observability_events": observability_events,
    }


def _execute_tool_task_for(role: Role):
    """Build a graph node that executes the role's task with tools."""

    def node(state: EkatraState) -> dict:
        workspace = _require_workspace(state)
        manager = TaskManager.from_dicts(state.get("tasks", []))
        pool = FixedAgentPool.from_dicts(state.get("agents", []))
        _attach_tools(pool, workspace)
        bus = _build_bus(state, pool)

        prior_count = len(state.get("communication", []))
        task = next(
            (
                t
                for t in manager.by_role(role)
                if t.status in {"PENDING", "ASSIGNED"}
            ),
            None,
        )

        agent = pool.get_by_role(role)

        if task is None:
            agent.send(
                MessageType.ERROR,
                f"No pending task for role {role.value}",
                recipient=pool.get_by_role(Role.PROJECT_MANAGER).agent_id,
            )
            message = f"[{agent.agent_id}] no pending task for role {role.value}"
            tasks = manager.to_dicts()
            agents = pool.to_dicts()
            return {
                "current_step": role.value,
                "tasks": tasks,
                "agents": agents,
                "messages": [message],
                "communication": bus.to_dicts()[prior_count:],
                "metrics": _compute_metrics(tasks, agents, 0),
                "tool_calls": [],
                "observability_events": [],
            }

        manager.assign(task.id, agent.agent_id)
        agent.receive_task(task.id)
        manager.start(task.id)

        agent.broadcast(
            MessageType.STATUS_UPDATE,
            f"{agent.agent_id} started task {task.id} ({role.value}).",
            related_task_id=task.id,
        )

        observability_events = [task_started_event(task.to_dict())]
        result = agent.execute(task)
        tool_records = [r.to_dict() for r in agent.tool_calls]

        if result.success:
            manager.complete(task.id, output=result.output)
            for recipient_role in _RESULT_RECIPIENTS[role][0]:
                recipient = pool.get_by_role(recipient_role)
                agent.send(
                    MessageType.RESULT,
                    f"[{task.id}] {result.output}",
                    related_task_id=task.id,
                    recipient=recipient.agent_id,
                )
            observability_events.extend(tool_executed_event(r) for r in tool_records)
            observability_events.append(task_completed_event(task.to_dict()))

        tasks = manager.to_dicts()
        agents = pool.to_dicts()
        return {
            "current_step": role.value,
            "tasks": tasks,
            "agents": agents,
            "messages": result.messages,
            "communication": bus.to_dicts()[prior_count:],
            "metrics": _compute_metrics(tasks, agents, len(tool_records)),
            "tool_calls": tool_records,
            "observability_events": observability_events,
        }

    return node


demo_architect = _execute_tool_task_for(Role.ARCHITECT)
demo_backend = _execute_tool_task_for(Role.BACKEND)
demo_frontend = _execute_tool_task_for(Role.FRONTEND)
demo_qa = _execute_tool_task_for(Role.QA)
demo_security = with_workflow_completed("security")(
    _execute_tool_task_for(Role.SECURITY)
)


def build_tools_graph():
    """Construct and compile the tool-assisted demo workflow graph."""
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(state_schema=EkatraState)

    builder.add_node("demo_plan", demo_plan)
    builder.add_node("demo_architect", demo_architect)
    builder.add_node("demo_backend", demo_backend)
    builder.add_node("demo_frontend", demo_frontend)
    builder.add_node("demo_qa", demo_qa)
    builder.add_node("demo_security", demo_security)

    builder.add_edge(START, "demo_plan")
    builder.add_edge("demo_plan", "demo_architect")
    builder.add_edge("demo_architect", "demo_backend")
    builder.add_edge("demo_backend", "demo_frontend")
    builder.add_edge("demo_frontend", "demo_qa")
    builder.add_edge("demo_qa", "demo_security")
    builder.add_edge("demo_security", END)

    return builder.compile()


def run_tools_demo(
    project_description: str,
    workspace_root: str,
) -> EkatraState:
    """Run the deterministic tool-assisted demo workflow.

    ``workspace_root`` must be an existing directory outside the project
    sources; every artifact is created inside it.
    """
    workspace = Workspace(workspace_root)
    state = create_initial_state(project_description)
    state["workspace_root"] = workspace.root
    return build_tools_graph().invoke(state)


def summarize(result: EkatraState) -> dict:
    """Return a compact observable summary of a demo workflow result."""
    from collections import Counter

    tool_calls = result.get("tool_calls", [])
    by_tool = Counter(tc["tool_name"] for tc in tool_calls)
    by_agent = Counter(tc["agent_id"] for tc in tool_calls)
    return {
        "tasks": len(result.get("tasks", [])),
        "tasks_completed": sum(
            1 for t in result.get("tasks", []) if t["status"] == "COMPLETED"
        ),
        "agents": len(result.get("agents", [])),
        "tool_calls": len(tool_calls),
        "tool_calls_ok": sum(1 for tc in tool_calls if tc["success"]),
        "tool_calls_failed": sum(1 for tc in tool_calls if not tc["success"]),
        "tool_calls_by_tool": dict(by_tool),
        "tool_calls_by_agent": dict(by_agent),
    }


def main() -> None:
    """Run the demo in a temporary workspace and print the summary."""
    with tempfile.TemporaryDirectory(prefix="ekatra-demo-") as root:
        result = run_tools_demo(EXAMPLE, root)
        print(json.dumps(summarize(result), indent=2))


if __name__ == "__main__":
    main()

__all__ = [
    "EXECUTION_ROLES",
    "EXAMPLE",
    "build_tools_graph",
    "demo_security",
    "demo_architect",
    "demo_backend",
    "demo_frontend",
    "demo_plan",
    "demo_qa",
    "run_tools_demo",
    "summarize",
]