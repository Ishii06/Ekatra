"""Core agent abstraction for Ekatra.

Defines the shared ``Agent`` base class, the agent ``Role`` and
``AgentStatus`` enums, and the uniform ``AgentExecutionResult`` produced by
every agent.

Execution defaults to deterministic mock behavior. The ``llm`` strategy
routes through the configured Gemini provider (see
``docs/decisions/ADR-006-gemini.md``); the ``tools`` strategy provides
tool-assisted deterministic execution. All three strategies share the same
public interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ekatra.orchestration.bus import MessageBus
    from ekatra.orchestration.message import AgentMessage, MessageType
    from ekatra.tasks.task import Task
    from ekatra.tools.base import ToolResult
    from ekatra.workspace import Workspace


class Role(str, Enum):
    """The six core agent roles of the Ekatra organization."""

    PROJECT_MANAGER = "project_manager"
    ARCHITECT = "architect"
    FRONTEND = "frontend"
    BACKEND = "backend"
    QA = "qa"
    SECURITY = "security"


class AgentStatus(str, Enum):
    """Agent lifecycle states (see ``docs/05-task-state-model.md``)."""

    CREATED = "CREATED"
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


def _role_label(role: Role) -> str:
    return str(role.value).replace("_", " ")


@dataclass
class AgentExecutionResult:
    """Uniform structured result returned by every agent execution."""

    agent_id: str
    task_id: str
    success: bool
    output: str
    messages: list[str] = field(default_factory=list)
    # Optional structured payload (e.g. planned task definitions).
    data: Any = None


class Agent:
    """Shared base class for all Ekatra agents.

    Attributes:
        agent_id: Stable unique identifier within the agent pool.
        role: The agent role (one of the six core roles).
        status: Current lifecycle status.
        current_task: ID of the task currently being executed, else None.
        metadata: Free-form metadata recorded during execution.
        strategy: Execution strategy ("mock" for this milestone).
        bus: Shared message bus attached by the orchestration layer, else None.
    """

    role: Role

    def __init__(
        self,
        agent_id: str,
        status: AgentStatus = AgentStatus.CREATED,
        current_task: str | None = None,
        metadata: dict[str, Any] | None = None,
        strategy: str = "mock",
    ) -> None:
        self.agent_id = agent_id
        self.status = status
        self.current_task = current_task
        self.metadata: dict[str, Any] = dict(metadata or {})
        self.strategy = strategy
        self.bus: MessageBus | None = None
        # Execution workspace and tools (attached by the orchestration layer).
        self.workspace: "Workspace | None" = None
        self.tools: dict[str, Any] = {}
        self.tool_policy: Any = None
        self.tool_calls: list[ToolResult] = []

    # -- execution ---------------------------------------------------------

    def receive_task(self, task_id: str) -> None:
        """Register a task as the agent's current task.

        Keeps ``current_task`` consistent with ``task.assigned_agent`` while
        the task is assigned. The agent is not yet ACTIVE; it becomes ACTIVE
        when execution starts via :meth:`execute`.
        """
        if self.status not in (AgentStatus.CREATED, AgentStatus.IDLE):
            raise ValueError(
                f"Agent {self.agent_id} is {self.status.value} and cannot receive a task"
            )
        self.current_task = task_id

    def execute(self, task: "Task") -> AgentExecutionResult:
        """Receive and execute a single task using the configured strategy.

        Deterministically returns an :class:`AgentExecutionResult`. No real
        LLM calls are made in this milestone.
        """
        if self.status not in (AgentStatus.CREATED, AgentStatus.IDLE):
            raise ValueError(
                f"Agent {self.agent_id} cannot execute while status is {self.status.value}"
            )

        self.status = AgentStatus.ACTIVE
        self.current_task = task.id

        try:
            output, messages = self._run(task)
        except Exception as exc:  # noqa: BLE001 - surface failures via result
            self.status = AgentStatus.IDLE
            self.current_task = None
            return AgentExecutionResult(
                agent_id=self.agent_id,
                task_id=task.id,
                success=False,
                output=f"Execution failed: {exc}",
                messages=[f"[{self.agent_id}] task {task.id} failed: {exc}"],
            )

        self.status = AgentStatus.COMPLETED
        self.current_task = None
        self.metadata["last_task_id"] = task.id
        return AgentExecutionResult(
            agent_id=self.agent_id,
            task_id=task.id,
            success=True,
            output=output,
            messages=messages,
        )

    def _run(self, task: "Task") -> tuple[str, list[str]]:
        """Dispatch a task to the configured execution strategy."""
        if self.strategy == "mock":
            return self._run_mock(task)
        if self.strategy == "tools":
            return self._run_tools(task)
        if self.strategy == "llm":
            return self._run_llm(task)
        raise ValueError(f"Unknown agent strategy: {self.strategy!r}")

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        """Deterministic mock implementation. Overridden by role agents."""
        output = f"{_role_label(self.role).title()} executed task {task.id}."
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        """Tool-assisted implementation. Overridden by role agents."""
        raise NotImplementedError(
            f"Tools execution strategy is not implemented for role {self.role.value}"
        )

    def _run_llm(self, task: "Task") -> tuple[str, list[str]]:
        """LLM-backed implementation routed through the Gemini provider.

        Requires ``GEMINI_API_KEY`` / ``GEMINI_MODEL`` to be configured; the
        documented mock and tool strategies never touch the provider.
        """
        from ekatra.config.settings import get_settings
        from ekatra.llm.gemini import GeminiProviderError, generate_text

        if not get_settings().has_api_key():
            raise GeminiProviderError(
                f"{self.agent_id}: LLM strategy requires GEMINI_API_KEY "
                "to be configured (environment or .env)."
            )
        prompt = (
            f"You are the {_role_label(self.role)} agent in the Ekatra "
            f"software-development organization.\n"
            f"Assigned task: {task.description}\n"
            "Return a concise report of the work you completed for this task."
        )
        output = generate_text(prompt)
        return output, [f"[{self.agent_id}] {output}"]

    # -- tool execution -----------------------------------------------------

    def attach_workspace(
        self,
        workspace: "Workspace",
        policy: Any = None,
    ) -> None:
        """Attach the execution workspace and this agent's tool set.

        ``policy`` is an explicit role permission policy
        (:class:`~ekatra.tools.registry.RoleToolPolicy`). When omitted, the
        role's default policy is used.
        """
        from ekatra.tools.files import build_default_tools
        from ekatra.tools.registry import role_policy_for

        self.workspace = workspace
        self.tools = build_default_tools(workspace)
        self.tool_policy = policy or role_policy_for(self.role.value)

    def use_tool(
        self,
        tool_name: str,
        *,
        task_id: str | None = None,
        **params: Any,
    ) -> ToolResult:
        """Run a workspace-bounded tool on behalf of this agent.

        Checks the role's explicit tool permission before executing, and
        records every (permitted) execution in ``self.tool_calls`` for
        observability.

        Raises:
            RuntimeError: When no workspace is attached.
            KeyError: When the tool is unknown.
            PermissionError: When the role is not allowed to use the tool.
        """
        if self.workspace is None:
            raise RuntimeError(
                f"Agent {self.agent_id} has no attached workspace"
            )
        if tool_name not in self.tools:
            raise KeyError(f"Unknown tool: {tool_name}")
        tool = self.tools[tool_name]
        path = params.get("path")
        if self.tool_policy is not None and not self.tool_policy.allows(tool_name, path):
            detail = f" on path {path!r}" if path else ""
            raise PermissionError(
                f"Agent {self.agent_id} (role {self.role.value}) cannot use "
                f"tool {tool_name!r}{detail}"
            )
        result = tool.execute(agent_id=self.agent_id, task_id=task_id, **params)
        self.tool_calls.append(result)
        self.metadata["tool_calls"] = len(self.tool_calls)
        return result

    # -- communication ------------------------------------------------------

    def attach_bus(self, bus: "MessageBus") -> None:
        """Attach the shared message bus so this agent can communicate.

        Attaching also registers the agent (if not already) as an allowed
        sender/recipient on the bus.
        """
        self.bus = bus
        bus.register_agent(self.agent_id)

    def send(
        self,
        message_type: "MessageType",
        content: str,
        recipient: str,
        related_task_id: str | None = None,
    ) -> "AgentMessage":
        """Send a structured message to another agent via the attached bus."""
        if self.bus is None:
            raise RuntimeError(f"Agent {self.agent_id} has no attached message bus")
        return self.bus.send(
            self.agent_id,
            recipient,
            message_type,
            content,
            related_task_id=related_task_id,
        )

    def broadcast(
        self,
        message_type: "MessageType",
        content: str,
        related_task_id: str | None = None,
    ) -> list["AgentMessage"]:
        """Broadcast a message to every agent except this agent."""
        if self.bus is None:
            raise RuntimeError(f"Agent {self.agent_id} has no attached message bus")
        return self.bus.broadcast(
            self.agent_id,
            message_type,
            content,
            related_task_id=related_task_id,
        )

    def read(self) -> list["AgentMessage"]:
        """Read this agent's undelivered mail from the attached bus."""
        if self.bus is None:
            raise RuntimeError(f"Agent {self.agent_id} has no attached message bus")
        return self.bus.read(self.agent_id)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for storage in the shared state."""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "current_task": self.current_task,
            "metadata": dict(self.metadata),
            "strategy": self.strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Agent":
        """Rebuild the correct concrete agent from a state dict."""
        from ekatra.agents.roles import ROLES

        role = Role(data["role"])
        agent_cls = ROLES[role]
        return agent_cls(
            agent_id=data["agent_id"],
            status=AgentStatus(data["status"]),
            current_task=data.get("current_task"),
            metadata=data.get("metadata") or {},
            strategy=data.get("strategy", "mock"),
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.agent_id} status={self.status.value}>"


__all__ = [
    "Agent",
    "AgentExecutionResult",
    "AgentStatus",
    "Role",
]