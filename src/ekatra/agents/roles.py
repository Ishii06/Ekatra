"""Concrete implementations of the six Ekatra agent roles.

Each role subclasses the shared Agent base and only customizes
deterministic mock behavior. Role-specific LLM prompting can be enabled via
the ``llm`` execution strategy (ADR-006) without changing the interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ekatra.agents.base import Agent, AgentExecutionResult, AgentStatus, Role

if TYPE_CHECKING:
    from ekatra.tasks.task import Task

# Fixed plan produced by the Project Manager.
# Dependencies are expressed as Role values so the PM node can map them to
# actual task IDs after creation.
_FIXED_PLAN = (
    {
        "role": Role.ARCHITECT,
        "description": "Define the system architecture and component interfaces.",
        "priority": 3,
        "complexity": 3,
        "risk": 10,
        "dependencies": [],
    },
    {
        "role": Role.BACKEND,
        "description": "Implement backend APIs, business logic, and data access.",
        "priority": 3,
        "complexity": 4,
        "risk": 25,
        "dependencies": [Role.ARCHITECT],
    },
    {
        "role": Role.FRONTEND,
        "description": "Implement frontend UI, components, and API integration.",
        "priority": 2,
        "complexity": 4,
        "risk": 15,
        "dependencies": [Role.BACKEND],
    },
    {
        "role": Role.QA,
        "description": "Execute tests, validate requirements, and report defects.",
        "priority": 3,
        "complexity": 2,
        "risk": 20,
        "dependencies": [Role.BACKEND, Role.FRONTEND],
    },
    {
        "role": Role.SECURITY,
        "description": "Perform security review and identify vulnerabilities.",
        "priority": 3,
        "complexity": 2,
        "risk": 40,
        "dependencies": [Role.BACKEND, Role.FRONTEND],
    },
)


class ProjectManagerAgent(Agent):
    """Planner: decomposes requirements into tasks and assigns roles."""

    role = Role.PROJECT_MANAGER

    def plan(self, description: str) -> AgentExecutionResult:
        """Produce a deterministic fixed task plan (mock planning).

        Returns the plan as structured data so the calling node can persist
        it through the TaskManager.
        """
        self.status = AgentStatus.ACTIVE
        plan = [dict(item) for item in _FIXED_PLAN]
        output = f"Planned {len(plan)} tasks for project {description!r}."
        labels = ", ".join(d["role"].value for d in plan)
        message = f"[{self.agent_id}] planned {len(plan)} tasks: {labels}."
        self.status = AgentStatus.COMPLETED
        self.metadata["planned_tasks"] = len(plan)
        return AgentExecutionResult(
            agent_id=self.agent_id,
            task_id="PLAN",
            success=True,
            output=output,
            messages=[message],
            data=plan,
        )


class ArchitectAgent(Agent):
    """Designs the system architecture and interfaces."""

    role = Role.ARCHITECT

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        output = (
            f"Defined system architecture for '{task.description}' - "
            "components, interfaces, and technology stack."
        )
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        content = (
            "# Architecture\n"
            "\n"
            f"Project: {task.description}\n"
            "\n"
            "## Components\n"
            "- Component: backend\n"
            "- Component: frontend\n"
            "\n"
            "## Interfaces\n"
            "- HTTP API between backend and frontend\n"
        )
        self.use_tool(
            "write_file",
            task_id=task.id,
            path="docs/architecture.md",
            content=content,
        )
        self.use_tool("list_dir", task_id=task.id, path="docs")
        output = (
            f"Defined system architecture in 'docs/architecture.md' for "
            f"'{task.description}'."
        )
        return output, [f"[{self.agent_id}] {output}"]


class BackendDeveloperAgent(Agent):
    """Implements backend APIs, business logic, and data access."""

    role = Role.BACKEND

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        output = (
            f"Implemented backend services for '{task.description}' - "
            "APIs, business logic, and data access."
        )
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        content = (
            "# Backend entry point\n"
            "\n"
            "def handle_request(name: str) -> str:\n"
            '    return f"Hello, {name}!"\n'
        )
        self.use_tool(
            "write_file",
            task_id=task.id,
            path="backend/main.py",
            content=content,
        )
        output = f"Implemented backend in 'backend/main.py' for '{task.description}'."
        return output, [f"[{self.agent_id}] {output}"]


class FrontendDeveloperAgent(Agent):
    """Implements the frontend UI, components, and API integration."""

    role = Role.FRONTEND

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        output = (
            f"Implemented frontend for '{task.description}' - "
            "UI, components, and API integration."
        )
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        content = (
            "# Frontend entry point\n"
            "\n"
            "def render_page(name: str) -> str:\n"
            '    return f"<h1>Hello, {name}!</h1>"\n'
        )
        self.use_tool(
            "write_file",
            task_id=task.id,
            path="frontend/app.py",
            content=content,
        )
        output = f"Implemented frontend in 'frontend/app.py' for '{task.description}'."
        return output, [f"[{self.agent_id}] {output}"]


class QaAgent(Agent):
    """Evaluates correctness and identifies defects."""

    role = Role.QA

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        output = f"Executed tests for '{task.description}' - all checks passed."
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        self.use_tool("read_file", task_id=task.id, path="backend/main.py")
        self.use_tool("read_file", task_id=task.id, path="frontend/app.py")
        content = (
            "# QA Report\n"
            "\n"
            "## Inspected artifacts\n"
            "- backend/main.py\n"
            "- frontend/app.py\n"
            "\n"
            "## Result\n"
            "All checks passed.\n"
        )
        self.use_tool(
            "write_file",
            task_id=task.id,
            path="docs/qa_report.md",
            content=content,
        )
        output = (
            f"Validated backend and frontend for '{task.description}' "
            "- all checks passed."
        )
        return output, [f"[{self.agent_id}] {output}"]


class SecurityAgent(Agent):
    """Reviews code for security risks and vulnerabilities."""

    role = Role.SECURITY

    def _run_mock(self, task: "Task") -> tuple[str, list[str]]:
        output = (
            f"Performed security review for '{task.description}' - "
            "no critical findings."
        )
        return output, [f"[{self.agent_id}] {output}"]

    def _run_tools(self, task: "Task") -> tuple[str, list[str]]:
        self.use_tool("read_file", task_id=task.id, path="backend/main.py")
        self.use_tool("read_file", task_id=task.id, path="frontend/app.py")
        self.use_tool("inspect_path", task_id=task.id, path="docs")
        content = (
            "# Security Report\n"
            "\n"
            "## Inspected artifacts\n"
            "- backend/main.py\n"
            "- frontend/app.py\n"
            "- docs\n"
            "\n"
            "## Findings\n"
            "No critical vulnerabilities found.\n"
        )
        self.use_tool(
            "write_file",
            task_id=task.id,
            path="docs/security_report.md",
            content=content,
        )
        output = (
            f"Performed security review for '{task.description}' "
            "- no critical findings."
        )
        return output, [f"[{self.agent_id}] {output}"]


# Registry: Role -> concrete Agent class
ROLES: dict[Role, type[Agent]] = {
    Role.PROJECT_MANAGER: ProjectManagerAgent,
    Role.ARCHITECT: ArchitectAgent,
    Role.FRONTEND: FrontendDeveloperAgent,
    Role.BACKEND: BackendDeveloperAgent,
    Role.QA: QaAgent,
    Role.SECURITY: SecurityAgent,
}

__all__ = [
    "ArchitectAgent",
    "BackendDeveloperAgent",
    "FrontendDeveloperAgent",
    "ProjectManagerAgent",
    "QaAgent",
    "ROLES",
    "SecurityAgent",
]