"""Controlled project workspace abstraction.

Provides :class:`Workspace` — a root directory representing the software
project under development. Every filesystem operation must go through the
workspace so that all read/write/list access stays inside the configured root:

* paths are resolved against the root and checked with
  :meth:`Path.is_relative_to`
* ``../`` traversal and absolute paths escaping the root raise
  :class:`PathTraversalError`
* ``os.sep``-style tricks and intermediate ``..`` segments are normalized by
  :func:`Path.resolve` before the containment check

The workspace is intentionally minimal: it exposes only the filesystem
primitives that the execution tools need. No arbitrary filesystem access is
introduced elsewhere in the codebase.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class PathTraversalError(ValueError):
    """Raised when a path attempts to escape the workspace root."""


class Workspace:
    """A safe, root-contained working directory for the Ekatra project.

    Attributes:
        root: The resolved absolute path of the workspace root.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- path containment ---------------------------------------------------

    def resolve(self, path: str | Path) -> Path:
        """Resolve ``path`` against the workspace root, rejecting escapes.

        Relative paths are joined to the root; absolute paths are checked
        directly. After normalization, any path that does not live inside the
        workspace root raises :class:`PathTraversalError`.
        """
        try:
            raw = Path(path)
            if raw.is_absolute():
                candidate = raw.resolve()
            else:
                candidate = (self.root / raw).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            raise PathTraversalError(
                f"Invalid path {path!r}: {exc}"
            ) from exc

        if candidate == self.root or self._is_within_root(candidate):
            return candidate
        raise PathTraversalError(
            f"Path {path!r} resolves outside the workspace root {self.root}"
        )

    def _is_within_root(self, candidate: Path) -> bool:
        try:
            candidate.relative_to(self.root)
            return True
        except ValueError:
            return False

    def relative(self, path: str | Path) -> Path:
        """Return the normalized path relative to the workspace root."""
        resolved = self.resolve(path)
        return resolved.relative_to(self.root)

    # -- filesystem primitives ---------------------------------------------

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        overwrite: bool = True,
    ) -> Path:
        """Write ``content`` to ``path`` inside the workspace.

        Missing parent directories are created. Raises
        :class:`PathTraversalError` when the path escapes the root.
        """
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {target}")
        target.write_text(content, encoding="utf-8", newline="\n")
        return target

    def read_text(self, path: str | Path) -> str:
        """Read and return the text content of a workspace file."""
        target = self.resolve(path)
        return target.read_text(encoding="utf-8")

    def exists(self, path: str | Path) -> bool:
        """Return True when the resolved workspace path exists."""
        try:
            return self.resolve(path).exists()
        except PathTraversalError:
            return False

    def is_dir(self, path: str | Path) -> bool:
        return self.resolve(path).is_dir()

    def is_file(self, path: str | Path) -> bool:
        return self.resolve(path).is_file()

    def list_dir(self, path: str | Path = ".") -> list[dict[str, Any]]:
        """List immediate entries of a workspace directory.

        Each entry is a dict with ``name``, ``type`` ("file"/"dir"), and the
        normalized ``path`` relative to the root.
        """
        target = self.resolve(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")
        entries: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda c: c.name.lower()):
            child_resolved = child.resolve()
            rel = child_resolved.relative_to(self.root)
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "path": rel.as_posix(),
                }
            )
        return entries

    def list_files(self, path: str | Path = ".") -> list[str]:
        """Return normalized relative paths of all files under ``path``."""
        files: list[str] = []
        target = self.resolve(path)
        for child in sorted(target.rglob("*"), key=lambda c: c.as_posix()):
            if child.is_file():
                rel = child.resolve().relative_to(self.root)
                files.append(rel.as_posix())
        return files

    def metadata(self, path: str | Path) -> dict[str, Any]:
        """Inspect a workspace path without exposing sensitive information.

        Returns a JSON-safe dict with size, modification time, and type.
        """
        target = self.resolve(path)
        stat = target.stat()
        return {
            "path": self.relative(path).as_posix(),
            "type": "dir" if target.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Workspace root={self.root}>"


def is_within(parent: str | Path, child: str | Path) -> bool:
    """Return True when ``child`` (resolved) is inside ``parent`` (resolved)."""
    parent_resolved = Path(parent).resolve()
    child_resolved = Path(child).resolve()
    try:
        child_resolved.relative_to(parent_resolved)
        return True
    except ValueError:
        return False


__all__ = ["Workspace", "PathTraversalError", "is_within"]