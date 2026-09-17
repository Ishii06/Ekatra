"""Tests for the tool interface and built-in file tools (Milestone 6).

Every tool validates its inputs, executes deterministically inside a bounded
workspace, and always returns a structured :class:`ToolResult` — including on
failure.
"""

from __future__ import annotations

import json

import pytest

from ekatra.tools import (
    Tool,
    ToolRegistry,
    build_default_tools,
)
from ekatra.workspace import Workspace


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    return Workspace(tmp_path / "proj")


def test_default_tool_set(workspace) -> None:
    tools = build_default_tools(workspace)
    assert set(tools) == {"read_file", "write_file", "list_dir", "inspect_path"}
    for tool in tools.values():
        assert isinstance(tool, Tool)
        assert tool.name
        assert tool.description


def test_registry_holds_tools(workspace) -> None:
    registry = ToolRegistry(workspace=workspace)
    assert registry.names() == ["inspect_path", "list_dir", "read_file", "write_file"]
    assert "write_file" in registry
    assert isinstance(registry.get("read_file"), Tool)
    with pytest.raises(KeyError):
        registry.get("unknown_tool")


def test_read_file_success(workspace) -> None:
    workspace.write_text("notes.md", "hello world")
    result = build_default_tools(workspace)["read_file"].execute(
        agent_id="a-1", task_id="T-1", path="notes.md"
    )
    assert result.success is True
    assert result.tool_name == "read_file"
    assert result.agent_id == "a-1"
    assert result.task_id == "T-1"
    assert result.output["content"] == "hello world"
    assert result.output["chars"] == 11


def test_read_missing_file_returns_failure(workspace) -> None:
    result = build_default_tools(workspace)["read_file"].execute(path="nope.txt")
    assert result.success is False
    assert result.error is not None
    assert result.output is None


def test_write_file_creates(workspace) -> None:
    result = build_default_tools(workspace)["write_file"].execute(
        path="docs/a.md", content="# A\n"
    )
    assert result.success is True
    assert result.output["created"] is True
    assert (workspace.root / "docs" / "a.md").is_file()


def test_write_file_overwrites(workspace) -> None:
    tools = build_default_tools(workspace)
    tools["write_file"].execute(path="a.txt", content="one")
    result = tools["write_file"].execute(path="a.txt", content="two")
    assert result.success is True
    assert result.output["created"] is False
    assert workspace.read_text("a.txt") == "two"


def test_write_file_requires_string_content(workspace) -> None:
    result = build_default_tools(workspace)["write_file"].execute(
        path="a.txt", content=12345
    )
    assert result.success is False
    assert "content must be a string" in result.error


def test_tools_require_string_path(workspace) -> None:
    tools = build_default_tools(workspace)
    result = tools["read_file"].execute(path=123)
    assert result.success is False
    assert "must be a string path" in result.error


def test_list_dir_result(workspace) -> None:
    workspace.write_text("docs/a.md", "a")
    workspace.write_text("src/main.py", "m")
    result = build_default_tools(workspace)["list_dir"].execute(path=".")
    assert result.success is True
    assert result.output["count"] == 2
    assert {e["name"] for e in result.output["entries"]} == {"docs", "src"}


def test_inspect_path_result(workspace) -> None:
    workspace.write_text("a.txt", "hello")
    result = build_default_tools(workspace)["inspect_path"].execute(path="a.txt")
    assert result.success is True
    assert result.output["type"] == "file"
    assert result.output["size_bytes"] == 5


def test_escaping_path_request_fails_as_result(workspace) -> None:
    result = build_default_tools(workspace)["read_file"].execute(path="../secret.txt")
    assert result.success is False
    assert "outside the workspace root" in result.error


def test_tool_result_structure_is_complete(workspace) -> None:
    result = build_default_tools(workspace)["inspect_path"].execute(
        agent_id="a-9", task_id="T-9", path="."
    )
    assert result.success is True
    assert result.timestamp
    assert result.duration_ms >= 0
    assert result.metadata == {}


def test_tool_result_is_json_serializable(workspace) -> None:
    result = build_default_tools(workspace)["inspect_path"].execute(
        agent_id="a-9", task_id="T-9", path="."
    )
    data = json.loads(json.dumps(result.to_dict()))
    assert data["success"] is True
    assert data["tool_name"] == "inspect_path"
    assert data["agent_id"] == "a-9"