"""Filesystem tools bounded to the project workspace.

Each tool wraps a :class:`~ekatra.workspace.Workspace` primitive. Malicious or
escaping paths are rejected by the workspace and surfaced as failed
:class:`ToolResult` instances (never as silent writes outside the root).
"""

from __future__ import annotations

from typing import Any

from ekatra.tools.base import Tool, ToolError
from ekatra.workspace import Workspace

_RESTRICTION_REASON = (
    "Tool input must be a string path resolvable inside the workspace"
)


class ReadFileTool(Tool):
    """Read and return the text content of a workspace file."""

    name = "read_file"
    description = "Read the UTF-8 text content of a file inside the workspace."

    def validate(self, path: Any, **params: Any) -> dict[str, Any]:
        if not isinstance(path, str) or not path.strip():
            raise ToolError(_RESTRICTION_REASON)
        return {"path": path}

    def run(self, path: str) -> dict[str, Any]:
        content = self.workspace.read_text(path)
        return {
            "path": self.workspace.relative(path).as_posix(),
            "content": content,
            "chars": len(content),
        }


class WriteFileTool(Tool):
    """Create or overwrite a UTF-8 text file inside the workspace."""

    name = "write_file"
    description = "Create or overwrite a UTF-8 text file inside the workspace."

    def validate(
        self,
        path: Any,
        content: Any,
        **params: Any,
    ) -> dict[str, Any]:
        if not isinstance(path, str) or not path.strip():
            raise ToolError(_RESTRICTION_REASON)
        if not isinstance(content, str):
            raise ToolError("write_file content must be a string")
        return {"path": path, "content": content}

    def run(self, path: str, content: str) -> dict[str, Any]:
        created = not self.workspace.exists(path)
        target = self.workspace.write_text(path, content)
        return {
            "path": self.workspace.relative(target).as_posix(),
            "bytes": len(content.encode("utf-8")),
            "created": created,
        }


class ListDirTool(Tool):
    """List immediate directory entries inside the workspace."""

    name = "list_dir"
    description = "List the immediate files and directories of a workspace folder."

    def validate(self, path: Any = ".", **params: Any) -> dict[str, Any]:
        if not isinstance(path, str):
            raise ToolError(_RESTRICTION_REASON)
        return {"path": path}

    def run(self, path: str) -> dict[str, Any]:
        entries = self.workspace.list_dir(path)
        return {
            "path": self.workspace.relative(path).as_posix(),
            "entries": entries,
            "count": len(entries),
        }


class InspectPathTool(Tool):
    """Inspect metadata for a workspace path."""

    name = "inspect_path"
    description = "Inspect size, type, and modification time of a workspace path."

    def validate(self, path: Any, **params: Any) -> dict[str, Any]:
        if not isinstance(path, str) or not path.strip():
            raise ToolError(_RESTRICTION_REASON)
        return {"path": path}

    def run(self, path: str) -> dict[str, Any]:
        return self.workspace.metadata(path)


TOOL_CLASSES: tuple[type[Tool], ...] = (
    ReadFileTool,
    WriteFileTool,
    ListDirTool,
    InspectPathTool,
)


def build_default_tools(workspace: Workspace) -> dict[str, Tool]:
    """Build the default tool set bound to ``workspace``."""
    return {cls.name: cls(workspace) for cls in TOOL_CLASSES}


__all__ = [
    "InspectPathTool",
    "ListDirTool",
    "ReadFileTool",
    "TOOL_CLASSES",
    "WriteFileTool",
    "build_default_tools",
]