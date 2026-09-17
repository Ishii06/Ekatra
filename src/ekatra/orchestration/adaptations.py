"""Apply adaptive decisions to the agent pool and task manager.

Mutates the pool (spawn/terminate), mutates the task manager (reassign/prioritize),
and returns an enriched ``AdaptiveDecision`` with ``affected_agent`` and
``resulting_state`` populated.
"""

from __future__ import annotations

from ekatra.agents.base import Role
from ekatra.orchestration.controller import SPAWNABLE_ROLES
from ekatra.orchestration.decisions import AdaptiveAction, AdaptiveDecision
from ekatra.orchestration.pool import AdaptiveAgentPool
from ekatra.tasks.manager import TaskManager


def apply_decision(
    decision: AdaptiveDecision,
    pool: AdaptiveAgentPool,
    manager: TaskManager,
) -> AdaptiveDecision:
    """Apply the adaptive decision in-place on the pool and task manager.

    Enriches the returned decision with ``affected_agent`` and
    ``resulting_state`` so the decision record is fully self-describing.
    """
    action = decision.decision

    if action is AdaptiveAction.SPAWN:
        target_role = Role(decision.affected_role) if decision.affected_role else None
        if target_role is not None and target_role in SPAWNABLE_ROLES:
            agent = pool.spawn(target_role)
            decision.affected_agent = agent.agent_id
            decision.resulting_state = {"spawned_agent": agent.agent_id, "role": target_role.value}

    elif action is AdaptiveAction.TERMINATE:
        agent_id = decision.affected_agent
        if agent_id:
            try:
                pool.terminate(agent_id)
                decision.resulting_state = {"terminated_agent": agent_id}
            except ValueError:
                decision.resulting_state = {"error": f"Could not terminate {agent_id}"}

    elif action is AdaptiveAction.REASSIGN:
        task_id = decision.affected_task
        agent_id = decision.affected_agent
        if task_id and agent_id:
            try:
                reassign_task(manager, task_id, agent_id)
                decision.resulting_state = {"reassigned_task": task_id, "to_agent": agent_id}
            except Exception as exc:
                decision.resulting_state = {"error": str(exc)}

    elif action is AdaptiveAction.PRIORITIZE:
        task_id = decision.affected_task
        if task_id:
            patch = decision.resulting_state or {}
            target_priority = patch.get("priority", 2)
            try:
                manager.set_priority(task_id, target_priority, reason=decision.reason)
                decision.resulting_state = {"prioritized_task": task_id, "priority": target_priority}
            except Exception as exc:
                decision.resulting_state = {"error": str(exc)}

    elif action is AdaptiveAction.CONTINUE:
        decision.resulting_state = {"action": "none"}

    return decision


def reassign_task(manager: TaskManager, task_id: str, new_agent_id: str) -> None:
    """Reassign a task to a different agent.

    The task is not restarted; it remains in its current status. The assignment
    field is updated so the correct agent picks it up in the next cycle.
    """
    task = manager.get(task_id)
    if task.assigned_agent == new_agent_id:
        return
    task.assigned_agent = new_agent_id


__all__ = ["apply_decision", "reassign_task"]