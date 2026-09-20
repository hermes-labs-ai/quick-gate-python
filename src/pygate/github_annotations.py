"""Render bounded GitHub Actions annotations for exact PyGate locations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

_MAX_FAILURES_BYTES = 1_000_000
_MAX_ANNOTATIONS = 100


def _escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(",", "%2C").replace(":", "%3A")


def _relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def render_annotations(failures_path: Path) -> list[str]:
    """Render only single-file findings with a positive, exact line number."""
    try:
        if failures_path.stat().st_size > _MAX_FAILURES_BYTES:
            return []
        payload = json.loads(failures_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list):
        return []
    annotations: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        files, line = finding.get("files"), finding.get("line")
        valid_line = isinstance(line, int) and not isinstance(line, bool) and line > 0
        if not isinstance(files, list) or len(files) != 1 or not valid_line:
            continue
        file_path = _relative_path(files[0])
        if file_path is None:
            continue
        properties = f"file={_escape(file_path)},line={line}"
        column = finding.get("column")
        if isinstance(column, int) and not isinstance(column, bool) and column > 0:
            properties += f",col={column}"
        annotations.append(f"::error {properties}::PyGate reported a diagnostic.")
        if len(annotations) == _MAX_ANNOTATIONS:
            break
    return annotations


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render PyGate file annotations")
    parser.add_argument("--failures", required=True)
    args = parser.parse_args(argv)
    for annotation in render_annotations(Path(args.failures)):
        print(annotation)


if __name__ == "__main__":
    main()
