"""Tests for the workspace abstraction (Milestone 6).

The workspace is the only way agents touch the filesystem. These tests verify
safe root-contained semantics, including path-traversal and absolute-path
protection.
"""

from __future__ import annotations

import pytest

from ekatra.workspace import PathTraversalError, Workspace, is_within


def test_workspace_creates_root(tmp_path) -> None:
    root = tmp_path / "proj"
    ws = Workspace(root)
    assert ws.root == root.resolve()
    assert ws.root.is_dir()


def test_write_and_read_round_trip(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("docs/notes.md", "# Notes\nhello")
    assert (ws.root / "docs" / "notes.md").is_file()
    assert ws.read_text("docs/notes.md") == "# Notes\nhello"


def test_write_creates_parent_directories(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("a/b/c.txt", "x")
    assert (ws.root / "a" / "b" / "c.txt").is_file()


def test_write_overwrites_by_default(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("a.txt", "one")
    ws.write_text("a.txt", "two")
    assert ws.read_text("a.txt") == "two"


def test_write_without_overwrite_raises(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("a.txt", "one")
    with pytest.raises(FileExistsError):
        ws.write_text("a.txt", "two", overwrite=False)


def test_read_modify_write(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("main.py", "x = 1\n")
    content = ws.read_text("main.py")
    ws.write_text("main.py", content + "y = 2\n")
    assert ws.read_text("main.py") == "x = 1\ny = 2\n"


def test_list_dir_reports_entries(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("docs/a.md", "a")
    ws.write_text("src/main.py", "m")
    by_name = {e["name"]: e for e in ws.list_dir(".")}
    assert set(by_name) == {"docs", "src"}
    assert by_name["docs"]["type"] == "dir"
    assert by_name["docs"]["path"] == "docs"
    assert by_name["src"]["type"] == "dir"


def test_list_dir_not_a_directory_raises(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("f.txt", "x")
    with pytest.raises(NotADirectoryError):
        ws.list_dir("f.txt")


def test_list_files_recursive(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("docs/a.md", "a")
    ws.write_text("src/x.py", "x")
    assert ws.list_files() == ["docs/a.md", "src/x.py"]


def test_metadata_is_json_safe(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("a.txt", "hello world")
    meta = ws.metadata("a.txt")
    assert meta["type"] == "file"
    assert meta["size_bytes"] == 11
    assert meta["path"] == "a.txt"


def test_path_traversal_raises(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    with pytest.raises(PathTraversalError):
        ws.resolve("../outside.txt")


def test_path_traversal_via_backslashes_raises(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    with pytest.raises(PathTraversalError):
        ws.resolve("..\\..\\outside.txt")


def test_absolute_path_outside_root_raises(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    outside = tmp_path / "outside.txt"
    with pytest.raises(PathTraversalError):
        ws.resolve(str(outside))


def test_absolute_path_inside_root_allowed(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    inside = ws.root / "hello.txt"
    ws.write_text(str(inside), "hi")
    assert ws.read_text(str(inside)) == "hi"


def test_relative_path_resolution(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    target = ws.resolve("nested/file.txt")
    assert target == (ws.root / "nested" / "file.txt")


def test_exists_and_type_helpers(tmp_path) -> None:
    ws = Workspace(tmp_path / "proj")
    ws.write_text("f.txt", "x")
    assert ws.exists("f.txt") is True
    assert ws.exists("../nope") is False
    assert ws.is_file("f.txt") is True
    assert ws.is_dir(".") is True


def test_is_within(tmp_path) -> None:
    parent = tmp_path / "parent"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    child = sub / "file.txt"
    child.write_text("x", encoding="utf-8")
    assert is_within(parent, child) is True
    assert is_within(parent, tmp_path / "other") is False