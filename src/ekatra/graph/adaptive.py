"""Adaptive LangGraph workflow for Ekatra.

Implements the adaptive orchestration loop described in ``docs/03``
and ``docs/04``:

    START
      ↓
    adaptive_plan        ← PM plans task set, assigns to baseline agents
      ↓
    adaptive_adapt       ← observer → controller → decision
      ↓
    adaptive_execute     ← execute pending tasks, spawn/terminate agents
      ↓
    remaining? ─── yes ─→ adaptive_adapt
         │
         no
         ↓
        END

The adaptive workflow reuses the fixed baseline PM plan and role agents
without modification. The controller is fully deterministic; no LLM is
invoked for resource-allocation decisions.
"""

from __future__ import annotations

from typing import Any

from ekatra.agents.base import AgentStatus, Role
from ekatra.observability.integration import (
    decision_events,
    task_assigned_event,
    task_completed_event,
    task_created_event,
    task_failed_event,
    task_started_event,
    workflow_completed_event,
    workflow_reached_terminal_state,
    workflow_started_event,
)
from ekatra.orchestration import (
    AdaptiveController,
    ControllerConfig,
    MessageBus,
    MessageType,
    SystemObservation,
    AdaptiveAgentPool,
    apply_decision,
    observe,
)
from ekatra.state.state import EkatraState
from ekatra.tasks import TaskManager


GRAPH_NAME = "ekatra_adaptive_workflow"


def _compute_metrics(tasks: list[dict], agents: list[dict], cycle: int) -> dict:
    """Produce observable metrics for the adaptive workflow."""
    return {
        "strategy": "adaptive",
        "tasks_created": len(tasks),
        "tasks_completed": sum(1 for t in tasks if t["status"] == "COMPLETED"),
        "agents": len(agents),
        "agents_active": sum(1 for a in agents if a["status"] == "ACTIVE"),
        "adaptive_cycle": cycle,
    }


def _build_bus(state: EkatraState, pool: AdaptiveAgentPool) -> MessageBus:
    """Rebuild the shared message bus from accumulated state."""
    bus = MessageBus.from_dicts(state.get("communication", []))
    for agent in pool.list_agents():
        agent.attach_bus(bus)
    return bus


_TERMINAL_TASK = {"COMPLETED", "CANCELLED"}


def _adopt_seeded_plan(
    state: EkatraState, description: str, seeded: list[dict]
) -> dict:
    """Assign a scenario-seeded task set to the adaptive agent pool.

    The seeded tasks become the workflow's authoritative task set (strategy is
    the only experimental variable). Every eligible task is assigned to its
    role's baseline agent in the pool; later controller cycles observe exactly
    this state and may spawn / terminate / reassign per the deterministic
    policy. Tasks in terminal states are left untouched.
    """
    pool = AdaptiveAgentPool()
    manager = TaskManager.from_dicts(seeded)
    pm = pool.get_by_role(Role.PROJECT_MANAGER)

    bus = _build_bus(state, pool)
    pm.broadcast(
        MessageType.STATUS_UPDATE,
        f"Adopted {len(manager.all())} planned tasks for {description!r}.",
    )

    assignable = [t for t in manager.all()
                  if t.status.value not in _TERMINAL_TASK]
    for task in assignable:
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
    return {
        "current_step": "adaptive_plan",
        "tasks": planned_tasks,
        "agents": pool.to_dicts(),
        "messages": [f"[{pm.agent_id}] adopted {len(planned_tasks)} tasks: {labels}."],
        "communication": bus.to_dicts(),
        "metrics": _compute_metrics(planned_tasks, pool.to_dicts(), 1),
        "adaptive_cycle": 1,
        "observability_events": observability_events,
    }


def adaptive_plan(state: EkatraState) -> dict:
    """Plan the task set and assign to baseline agents.

    Identical to the fixed workflow's project_manager_node but uses
    the AdaptiveAgentPool. When the incoming state already carries a
    pre-seeded task set (Milestone 8 experiment harness), the seeded tasks are
    adopted and assigned instead of calling ``pm.plan()``; the controller /
    adaptive loop then operates on exactly the scenario's task set.
    """
    description = state.get("project_description", "")
    seeded = state.get("tasks")
    if seeded:
        return _adopt_seeded_plan(state, description, seeded)

    pool = AdaptiveAgentPool()
    manager = TaskManager()
    pm = pool.get_by_role(Role.PROJECT_MANAGER)
    result = pm.plan(description)

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

    planned_tasks = manager.to_dicts()
    observability_events = [workflow_started_event(description)]
    observability_events.extend(task_created_event(t) for t in planned_tasks)
    observability_events.extend(task_assigned_event(t) for t in planned_tasks)

    return {
        "current_step": "adaptive_plan",
        "tasks": planned_tasks,
        "agents": pool.to_dicts(),
        "messages": result.messages,
        "communication": bus.to_dicts(),
        "metrics": _compute_metrics(planned_tasks, pool.to_dicts(), 1),
        "adaptive_cycle": 1,
        "observability_events": observability_events,
    }


def adaptive_adapt(state: EkatraState) -> dict:
    """Observe the current state and decide on an adaptive action."""
    tasks = state.get("tasks", [])
    agents = state.get("agents", [])
    cycle = state.get("adaptive_cycle", 1)

    pool = AdaptiveAgentPool.from_dicts(agents)
    manager = TaskManager.from_dicts(tasks)
    bus = _build_bus(state, pool)

    observation = observe(tasks, agents)
    controller = AdaptiveController(ControllerConfig())

    agent_counts = pool.agent_counts()
    decision = controller.evaluate(
        observation,
        agent_counts=agent_counts,
        all_agents=agents,
        tasks=tasks,
        cycle=cycle,
    )

    # Apply the decision to pool and task manager
    apply_decision(decision, pool, manager)

    # PM communicates the decision
    prior_count = len(state.get("communication", []))
    pm = pool.get_by_role(Role.PROJECT_MANAGER)
    pm.broadcast(
        MessageType.STATUS_UPDATE,
        f"Cycle {cycle}: decision={decision.decision.value}, reason={decision.reason}",
    )

    # Serialize the enriched decision for the state
    decision_dict = decision.to_dict()
    decision_dict["cycle"] = cycle

    # Emit the adaptive decision and its concrete action event(s) (spawn,
    # terminate, reassign, prioritize) in a single shared code path.
    observability_events = decision_events(decision_dict)

    return {
        "current_step": "adaptive_adapt",
        "tasks": manager.to_dicts(),
        "agents": pool.to_dicts(),
        "messages": [f"[adaptive] Cycle {cycle}: {decision.decision.value}"],
        "communication": bus.to_dicts()[prior_count:],
        "adaptive_decisions": [decision_dict],
        "metrics": _compute_metrics(manager.to_dicts(), pool.to_dicts(), cycle),
        "adaptive_cycle": cycle,
        "observability_events": observability_events,
    }


def adaptive_execute(state: EkatraState) -> dict:
    """Execute all pending tasks using the current agent pool."""
    tasks = state.get("tasks", [])
    agents = state.get("agents", [])
    cycle = state.get("adaptive_cycle", 1)

    pool = AdaptiveAgentPool.from_dicts(agents)
    manager = TaskManager.from_dicts(tasks)
    bus = _build_bus(state, pool)

    prior_count = len(state.get("communication", []))

    EXECUTION_ROLES = (
        Role.ARCHITECT,
        Role.BACKEND,
        Role.FRONTEND,
        Role.QA,
        Role.SECURITY,
    )

    _RESULT_RECIPIENTS: dict[Role, tuple[list[Role], MessageType]] = {
        Role.ARCHITECT: ([Role.BACKEND, Role.FRONTEND], MessageType.RESULT),
        Role.BACKEND: ([Role.FRONTEND, Role.QA, Role.SECURITY], MessageType.RESULT),
        Role.FRONTEND: ([Role.QA, Role.SECURITY], MessageType.RESULT),
        Role.QA: ([Role.BACKEND, Role.FRONTEND], MessageType.REVIEW_FEEDBACK),
        Role.SECURITY: ([Role.PROJECT_MANAGER], MessageType.RESULT),
    }

    all_messages: list[str] = []
    observability_events: list[dict[str, Any]] = []
    for role in EXECUTION_ROLES:
        pending_tasks = [
            t for t in manager.by_role(role)
            if t.status in {"PENDING", "ASSIGNED", "RETRY"}
        ]
        if not pending_tasks:
            continue

        idle_agents = pool.available_for(role)
        if not idle_agents:
            continue

        agent = idle_agents[0]
        task = pending_tasks[0]

        manager.assign(task.id, agent.agent_id)
        agent.receive_task(task.id)
        manager.start(task.id)
        observability_events.append(task_started_event(task.to_dict()))

        agent.broadcast(
            MessageType.STATUS_UPDATE,
            f"{agent.agent_id} started task {task.id} ({role.value}).",
            related_task_id=task.id,
        )

        result = agent.execute(task)

        if result.success:
            manager.complete(task.id, output=result.output)
            recipients, message_type = _RESULT_RECIPIENTS[role]
            for recipient_role in recipients:
                try:
                    recipient = pool.get_by_role(recipient_role)
                    agent.send(
                        message_type,
                        f"[{task.id}] {result.output}",
                        related_task_id=task.id,
                        recipient=recipient.agent_id,
                    )
                except ValueError:
                    pass
            executed = task.to_dict()
            observability_events.append(task_completed_event(executed))
        else:
            observability_events.append(task_failed_event(task.to_dict()))

        # Reset to IDLE for multi-round reuse
        agent.status = AgentStatus.IDLE
        agent.current_task = None

        all_messages.extend(result.messages)

    final_tasks = manager.to_dicts()
    if workflow_reached_terminal_state(final_tasks):
        observability_events.append(workflow_completed_event("adaptive_execute"))

    return {
        "current_step": "adaptive_execute",
        "tasks": final_tasks,
        "agents": pool.to_dicts(),
        "messages": all_messages,
        "communication": bus.to_dicts()[prior_count:],
        "metrics": _compute_metrics(final_tasks, pool.to_dicts(), cycle),
        "adaptive_cycle": cycle + 1,
        "observability_events": observability_events,
    }


def _should_continue(state: EkatraState) -> str:
    """Route function: return 'adaptive_adapt' if tasks remain, else 'end'.

    ``adaptive_execute`` increments ``adaptive_cycle`` after every round, so a
    run performs at most ``max_adaptive_rounds`` execute/adapt cycles: the guard
    stops after the round that leaves ``adaptive_cycle`` one past the limit.
    The loop also terminates as soon as the workflow reaches its terminal
    execution state (no executable work remains), even before the round limit,
    and it always terminates even when tasks never fully complete (e.g. stuck
    FAILED tasks in experiment scenarios).
    """
    from ekatra.config.settings import get_settings

    max_rounds = get_settings().max_adaptive_rounds
    cycle = state.get("adaptive_cycle", 1)
    tasks = state.get("tasks", [])

    # Stop when terminal execution state is reached or the round limit is spent
    # (cycle is already incremented past the last executed round, so the run
    # permits exactly max_adaptive_rounds cycles - no more, no hidden extra one).
    if workflow_reached_terminal_state(tasks) or cycle > max_rounds:
        return "end"
    return "adaptive_adapt"


def build_adaptive_graph():
    """Construct and compile the adaptive workflow graph."""
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(state_schema=EkatraState)

    builder.add_node("adaptive_plan", adaptive_plan)
    builder.add_node("adaptive_adapt", adaptive_adapt)
    builder.add_node("adaptive_execute", adaptive_execute)

    builder.add_edge(START, "adaptive_plan")
    builder.add_edge("adaptive_plan", "adaptive_adapt")
    builder.add_edge("adaptive_adapt", "adaptive_execute")
    builder.add_conditional_edges(
        "adaptive_execute",
        _should_continue,
        {"adaptive_adapt": "adaptive_adapt", "end": END},
    )

    return builder.compile()


def create_adaptive_initial_state(project_description: str) -> EkatraState:
    """Create initial state for the adaptive workflow."""
    from ekatra.state.state import create_initial_state
    s = create_initial_state(project_description)
    s["adaptive_cycle"] = 1
    return s


def run_adaptive(
    project_description: str | None = None,
    *,
    initial_state: EkatraState | dict[str, Any] | None = None,
) -> EkatraState:
    """Execute the adaptive workflow and return the final state.

    Args:
        project_description: Project description when no initial state is given.
        initial_state: Optional pre-built state (e.g. a scenario-seeded state
            from the experiment harness). ``adaptive_cycle`` is initialized to
            1 when missing.
    """
    graph = build_adaptive_graph()
    if initial_state is not None:
        prepared = dict(initial_state)
        prepared.setdefault("adaptive_cycle", 1)
        return graph.invoke(prepared)
    initial = create_adaptive_initial_state(project_description or "")
    return graph.invoke(initial)


__all__ = [
    "GRAPH_NAME",
    "adaptive_plan",
    "adaptive_adapt",
    "adaptive_execute",
    "build_adaptive_graph",
    "create_adaptive_initial_state",
    "run_adaptive",
]