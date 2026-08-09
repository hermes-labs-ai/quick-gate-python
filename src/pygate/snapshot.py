from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_SKIP_DIRS = {".git", ".pygate", "__pycache__", ".venv", "venv", "node_modules"}


def _relative(path: Path, cwd: Path) -> str:
    try:
        return path.absolute().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        return path.absolute().as_posix()


def _files_for_path(path: Path) -> list[Path]:
    if path.is_file() or path.is_symlink():
        return [path]
    if not path.is_dir():
        return [path]
    files: list[Path] = []
    for root, dirs, names in os.walk(path, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            files.append(Path(root) / name)
    return files


def snapshot_digest(checked_paths: list[str], *, cwd: Path) -> tuple[str, list[str]]:
    """Hash checked input bytes and return the canonical path list.

    Missing paths are included as explicit records, so a later creation or
    deletion changes the digest rather than silently disappearing.
    """

    requested = checked_paths
    records: list[dict[str, Any]] = []
    normalized: set[str] = set()
    for raw_path in requested:
        path = Path(raw_path)
        if not path.is_absolute():
            path = cwd / path
        files = _files_for_path(path)
        if not files:
            files = [path]
        for file_path in files:
            relative = _relative(file_path, cwd)
            if relative in normalized:
                continue
            normalized.add(relative)
            if file_path.is_symlink():
                records.append(
                    {
                        "path": relative,
                        "exists": True,
                        "symlink": os.readlink(file_path),
                    }
                )
                continue
            if not file_path.exists() or not file_path.is_file():
                records.append({"path": relative, "exists": False})
                continue
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                records.append({"path": relative, "exists": False, "error": type(exc).__name__})
                continue
            records.append(
                {
                    "path": relative,
                    "exists": True,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    records.sort(key=lambda record: record["path"])
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), [record["path"] for record in records]


def config_digest(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
