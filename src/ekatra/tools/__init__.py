"""Workspace-bounded execution tools for Ekatra agents.

Defines the tool interface (:class:`~ekatra.tools.base.Tool`), the structured
:class:`~ekatra.tools.base.ToolResult`, the tool set
(:mod:`ekatra.tools.files`), and the explicit per-role permission registry
(:mod:`ekatra.tools.registry`).

Tools are the *only* way agents touch the filesystem. They operate strictly
inside a :class:`~ekatra.workspace.Workspace` and never expose raw shell access.
"""

from ekatra.tools.base import Tool, ToolError, ToolResult
from ekatra.tools.files import (
    InspectPathTool,
    ListDirTool,
    ReadFileTool,
    TOOL_CLASSES,
    WriteFileTool,
    build_default_tools,
)
from ekatra.tools.registry import (
    ALLOWED_TOOLS,
    RoleToolPolicy,
    ToolRegistry,
    WRITE_PREFIXES,
    role_policy_for,
)

__all__ = [
    "ALLOWED_TOOLS",
    "InspectPathTool",
    "ListDirTool",
    "ReadFileTool",
    "RoleToolPolicy",
    "TOOL_CLASSES",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "WRITE_PREFIXES",
    "WriteFileTool",
    "build_default_tools",
    "role_policy_for",
]