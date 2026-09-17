"""Fixed baseline workflow nodes for Ekatra.

Workflow (sequential, no dynamic routing):

    START
      ↓
    project_manager
      ↓
    architect
      ↓
    backend
      ↓
    frontend
      ↓
    qa
      ↓
    security
      ↓
    END

The Project Manager node plans a deterministic task set and assigns each task
to its role's fixed agent. Each remaining role node then drains every task it
can currently start: the role's single static agent sequentially executes all
PENDING / ASSIGNED / RETRY tasks whose dependencies are satisfied (the fixed
baseline is a static six-agent organization that completes the supplied
workload). No real LLM calls are made in the fixed workflow.

Agents communicate through an in-memory :class:`MessageBus` that is rebuilt by
every node from the accumulated state ``communication`` field, so the message
history is preserved and observable across the whole run.
"""

from __future__ import annotations

from ekatra.agents import AgentStatus, FixedAgentPool, ProjectManagerAgent, Role
from ekatra.observability.integration import (
    task_assigned_event,
    task_completed_event,
    task_created_event,
    task_failed_event,
    task_started_event,
    workflow_started_event,
    with_workflow_completed,
)
from ekatra.orchestration import MessageBus, MessageType
from ekatra.state.state import EkatraState
from ekatra.tasks import TaskManager

EXECUTION_ROLES = (
    Role.ARCHITECT,
    Role.BACKEND,
    Role.FRONTEND,
    Role.QA,
    Role.SECURITY,
)

# Which roles receive a completion message from each executing role.
_RESULT_RECIPIENTS: dict[Role, tuple[list[Role], MessageType]] = {
    Role.ARCHITECT: ([Role.BACKEND, Role.FRONTEND], MessageType.RESULT),
    Role.BACKEND: ([Role.FRONTEND, Role.QA, Role.SECURITY], MessageType.RESULT),
    Role.FRONTEND: ([Role.QA, Role.SECURITY], MessageType.RESULT),
    Role.QA: ([Role.BACKEND, Role.FRONTEND], MessageType.REVIEW_FEEDBACK),
    Role.SECURITY: ([Role.PROJECT_MANAGER], MessageType.RESULT),
}


def _compute_metrics(tasks: list[dict], agents: list[dict]) -> dict:
    """Produce simple observable metrics about the current state."""
    return {
        "strategy": "fixed",
        "tasks_created": len(tasks),
        "tasks_completed": sum(1 for t in tasks if t["status"] == "COMPLETED"),
        "agents": len(agents),
        "agents_active": sum(1 for a in agents if a["status"] == "ACTIVE"),
    }


def _build_bus(state: EkatraState, pool: FixedAgentPool, *, with_agents: bool) -> MessageBus:
    """Rebuild the shared message bus from accumulated state.

    The bus is registered with every pool agent so each one can send, receive,
    and broadcast during this node.
    """
    bus = MessageBus.from_dicts(state.get("communication", []))
    if with_agents:
        for agent in pool.list_agents():
            agent.attach_bus(bus)
    return bus


_TERMINAL_TASK = {"COMPLETED", "CANCELLED"}


def _adopt_seeded_plan(
    state: EkatraState, description: str, seeded: list[dict]
) -> dict:
    """Assign a scenario-seeded task set to the fixed baseline organization.

    Every eligible task is assigned to its role's single baseline agent (one
    per role). Tasks in terminal states are left untouched. No spawning and no
    plan re-generation occur; each role node later drains every task it can
    start within its one visit.
    """
    pool = FixedAgentPool()
    manager = TaskManager.from_dicts(seeded)
    pm = pool.get_by_role(Role.PROJECT_MANAGER)
    bus = _build_bus(state, pool, with_agents=True)

    pm.broadcast(
        MessageType.STATUS_UPDATE,
        f"Adopted {len(manager.all())} planned tasks for {description!r}.",
    )

    assignable = {task.id for task in manager.all()
                  if task.status.value not in _TERMINAL_TASK}
    for task_id in assignable:
        task = manager.get(task_id)
        agent = pool.get_by_role(task.role)
        agent.receive_task(task.id)
        agent.metadata["assigned_task_id"] = task.id
        manager.assign(task.id, agent.agent_id)
        pm.send(
            MessageType.TASK_ASSIGNMENT,
            f"Assigned {task.id} ({task.role.value}) to you: {task.description}",
            related_task_id=task.id,
            recipient=agent.agent_id,
        )

    planned_tasks = manager.to_dicts()
    observability_events = [workflow_started_event(description)]
    observability_events.extend(task_created_event(t) for t in planned_tasks)
    observability_events.extend(task_assigned_event(t) for t in planned_tasks)

    labels = ", ".join(t["role"] for t in planned_tasks)
    message = f"[{pm.agent_id}] adopted {len(planned_tasks)} tasks: {labels}."
    return {
        "current_step": Role.PROJECT_MANAGER.value,
        "tasks": planned_tasks,
        "agents": pool.to_dicts(),
        "messages": [message],
        "communication": bus.to_dicts(),
        "metrics": _compute_metrics(planned_tasks, pool.to_dicts()),
        "observability_events": observability_events,
    }


def project_manager_node(state: EkatraState) -> dict:
    """Plan the fixed task set, assign tasks, and notify every agent.

    When the incoming state already carries a pre-seeded task set (Milestone 8
    experiment harness), the node adopts those tasks instead of re-planning:
    the PM assigns every eligible task to its role's fixed baseline agent. This
    is the ``state-driven`` counterpart of the default ``pm.plan()`` path and it
    never spawns or terminates agents. See ``docs/decisions/ADR-005``.
    """
    description = state.get("project_description", "")
    seeded = state.get("tasks")
    if seeded:
        return _adopt_seeded_plan(state, description, seeded)

    pool = FixedAgentPool()
    manager = TaskManager()
    pm = pool.get_by_role(Role.PROJECT_MANAGER)
    result = pm.plan(description)

    bus = _build_bus(state, pool, with_agents=True)
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

    planned_tasks = manager.to_dicts()
    observability_events = [workflow_started_event(description)]
    observability_events.extend(task_created_event(t) for t in planned_tasks)
    observability_events.extend(task_assigned_event(t) for t in planned_tasks)

    return {
        "current_step": Role.PROJECT_MANAGER.value,
        "tasks": planned_tasks,
        "agents": pool.to_dicts(),
        "messages": result.messages,
        "communication": bus.to_dicts(),
        "metrics": _compute_metrics(planned_tasks, pool.to_dicts()),
        "observability_events": observability_events,
    }


def _execute_task_for(role: Role):
    """Build a graph node that drains all startable tasks for the fixed role.

    The single static agent repeatedly picks a PENDING / ASSIGNED / RETRY task
    whose dependencies are satisfied, executes it, and resets to IDLE until no
    more tasks can be started.  FAILED tasks are never selected — the fixed
    baseline does not recover from failures.
    """

    def node(state: EkatraState) -> dict:
        manager = TaskManager.from_dicts(state.get("tasks", []))
        pool = FixedAgentPool.from_dicts(state.get("agents", []))
        bus = _build_bus(state, pool, with_agents=True)

        prior_count = len(state.get("communication", []))
        agent = pool.get_by_role(role)

        all_messages: list[str] = []
        observability_events: list[dict] = []

        while True:
            candidates = [
                t
                for t in manager.by_role(role)
                if t.status in {"PENDING", "ASSIGNED", "RETRY"}
                and manager.dependencies_satisfied(t)
            ]
            if not candidates:
                break

            task = candidates[0]

            manager.assign(task.id, agent.agent_id)
            agent.receive_task(task.id)
            manager.start(task.id)

            agent.broadcast(
                MessageType.STATUS_UPDATE,
                f"{agent.agent_id} started task {task.id} ({role.value}).",
                related_task_id=task.id,
            )

            observability_events.append(task_started_event(task.to_dict()))
            result = agent.execute(task)

            if result.success:
                manager.complete(task.id, output=result.output)
                recipients, message_type = _RESULT_RECIPIENTS[role]
                for recipient_role in recipients:
                    recipient = pool.get_by_role(recipient_role)
                    agent.send(
                        message_type,
                        f"[{task.id}] {result.output}",
                        related_task_id=task.id,
                        recipient=recipient.agent_id,
                    )
            else:
                observability_events.append(task_failed_event(task.to_dict()))

            tasks_after = manager.to_dicts()
            for executed in tasks_after:
                if executed["id"] == task.id and executed.get("status") == "COMPLETED":
                    observability_events.append(task_completed_event(executed))

            all_messages.extend(result.messages)

            # Reset to IDLE for multi-task reuse within this node.
            agent.status = AgentStatus.IDLE
            agent.current_task = None

        if all_messages:
            # Leave the agent in COMPLETED status after the final task.
            agent.status = AgentStatus.COMPLETED
            agent.current_task = None
        else:
            agent.send(
                MessageType.ERROR,
                f"No pending task for role {role.value}",
                recipient=pool.get_by_role(Role.PROJECT_MANAGER).agent_id,
            )
            all_messages.append(
                f"[{agent.agent_id}] no pending task for role {role.value}"
            )

        tasks_final = manager.to_dicts()

        return {
            "current_step": role.value,
            "tasks": tasks_final,
            "agents": pool.to_dicts(),
            "messages": all_messages,
            "communication": bus.to_dicts()[prior_count:],
            "metrics": _compute_metrics(tasks_final, pool.to_dicts()),
            "observability_events": observability_events,
        }

    return node


architect_node = _execute_task_for(Role.ARCHITECT)
backend_node = _execute_task_for(Role.BACKEND)
frontend_node = _execute_task_for(Role.FRONTEND)
qa_node = _execute_task_for(Role.QA)
security_node = with_workflow_completed("security")(
    _execute_task_for(Role.SECURITY)
)

__all__ = [
    "project_manager_node",
    "architect_node",
    "backend_node",
    "frontend_node",
    "qa_node",
    "security_node",
]