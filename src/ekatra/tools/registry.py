"""Tool registry and explicit per-role tool permissions.

Roles receive only the tools they need:

* Project Manager — inspection only (never modifies source)
* Architect — creates architecture artifacts under ``docs/``
* Backend — writes under ``backend/``
* Frontend — writes under ``frontend/``
* QA — inspects anything, writes reports under ``docs/``
* Security — inspects anything, writes findings under ``docs/``

Write permissions are kept explicit per role: ``write_file`` is only granted
when the target path starts with one of the role's allowed prefixes. Reading,
listing, and metadata inspection are granted to every role.
"""

from __future__ import annotations

from typing import Any

from ekatra.workspace import Workspace

from ekatra.tools.files import build_default_tools

# Role keys are the string values of ``Role`` ("project_manager", ...) so this
# module never imports the agent layer (which itself imports the tools layer).
ALLOWED_TOOLS: dict[str, set[str]] = {
    "project_manager": {"read_file", "list_dir", "inspect_path"},
    "architect": {"read_file", "write_file", "list_dir", "inspect_path"},
    "backend": {"read_file", "write_file", "list_dir", "inspect_path"},
    "frontend": {"read_file", "write_file", "list_dir", "inspect_path"},
    "qa": {"read_file", "write_file", "list_dir", "inspect_path"},
    "security": {"read_file", "write_file", "list_dir", "inspect_path"},
}

WRITE_PREFIXES: dict[str, tuple[str, ...]] = {
    "project_manager": (),
    "architect": ("docs/",),
    "backend": ("backend/",),
    "frontend": ("frontend/",),
    "qa": ("docs/",),
    "security": ("docs/",),
}


def _role_value(role: Any) -> str:
    """Normalize a ``Role`` enum or plain string to its string value."""
    return str(getattr(role, "value", role))


class RoleToolPolicy:
    """Immutable permission set for a single agent role."""

    def __init__(
        self,
        role: Any,
        allowed_tools: set[str],
        write_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.role = _role_value(role)
        self.allowed_tools = frozenset(allowed_tools)
        self.write_prefixes = write_prefixes

    def allows(self, tool_name: str, path: str | None = None) -> bool:
        """Return True when this role may run ``tool_name`` (with ``path``)."""
        if tool_name not in self.allowed_tools:
            return False
        if tool_name == "write_file" and path is not None:
            return any(path.startswith(prefix) for prefix in self.write_prefixes)
        return True

    def __repr__(self) -> str:
        tools = ", ".join(sorted(self.allowed_tools))
        return f"<RoleToolPolicy {self.role} [{tools}]>"


def role_policy_for(role: Any) -> RoleToolPolicy:
    """Return the explicit policy for a role by enum or string value."""
    role_value = _role_value(role)
    if role_value not in ALLOWED_TOOLS:
        raise KeyError(f"No tool policy for role {role_value!r}")
    return RoleToolPolicy(
        role=role_value,
        allowed_tools=set(ALLOWED_TOOLS[role_value]),
        write_prefixes=WRITE_PREFIXES.get(role_value, ()),
    )


class ToolRegistry:
    """Holds the tool set bound to a single workspace."""

    def __init__(
        self,
        tools: dict[str, Any] | None = None,
        workspace: Workspace | None = None,
    ) -> None:
        if tools is not None:
            self.tools = dict(tools)
        else:
            if workspace is None:
                raise ValueError("A workspace is required to build default tools")
            self.tools = build_default_tools(workspace)
        self.workspace = workspace

    def get(self, tool_name: str) -> Any:
        try:
            return self.tools[tool_name]
        except KeyError:
            raise KeyError(f"Unknown tool: {tool_name}") from None

    def names(self) -> list[str]:
        return sorted(self.tools)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self.tools


__all__ = [
    "ALLOWED_TOOLS",
    "RoleToolPolicy",
    "ToolRegistry",
    "WRITE_PREFIXES",
    "role_policy_for",
]