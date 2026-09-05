from __future__ import annotations

import re
from pathlib import Path

from pygate.exec import run_command
from pygate.models import FailuresPayload, GateName

_EXCLUDED_DIRS = re.compile(r"(^|/)(\.(pygate|git|venv|tox|nox)|__pycache__|dist|build|node_modules)(/|$)")
_PARENT_COMPONENT = re.compile(r"(^|[/\\])\.\.([/\\]|$)")
_MAX_FILES = 20


def _is_eligible(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    if _EXCLUDED_DIRS.search(path):
        return False
    return not (path.startswith("/") or _PARENT_COMPONENT.search(path))


def _collect_scoped_files(failures: FailuresPayload) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []

    for f in failures.changed_files:
        if f not in seen and _is_eligible(f):
            seen.add(f)
            files.append(f)

    for finding in failures.findings:
        for f in finding.files:
            if f not in seen and _is_eligible(f):
                seen.add(f)
                files.append(f)

    return files[:_MAX_FILES]


def run_deterministic_prefix(*, cwd: Path, failures: FailuresPayload) -> list[dict]:
    actions: list[dict] = []

    has_lint_failure = any(f.gate == GateName.LINT for f in failures.findings)
    if not has_lint_failure:
        return actions

    scoped_files = _collect_scoped_files(failures)
    if not scoped_files:
        return actions

    # ruff check --fix (safe fixes only)
    fix_trace = run_command(["ruff", "check", "--fix", *scoped_files], cwd=cwd)
    actions.append(
        {
            "rule_id": "RUFF_AUTOFIX",
            "strategy": "deterministic_prefix",
            "accepted": fix_trace.exit_code in (0, 1),  # ruff returns 1 if unfixed issues remain
            "command": fix_trace.command,
            "exit_code": fix_trace.exit_code,
            "files": scoped_files,
            "rationale": "Apply safe ruff fixes on scoped files to clear auto-fixable lint issues.",
        }
    )

    # ruff format
    fmt_trace = run_command(["ruff", "format", *scoped_files], cwd=cwd)
    actions.append(
        {
            "rule_id": "RUFF_FORMAT",
            "strategy": "deterministic_prefix",
            "accepted": fmt_trace.exit_code == 0,
            "command": fmt_trace.command,
            "exit_code": fmt_trace.exit_code,
            "files": scoped_files,
            "rationale": "Apply ruff formatting on scoped files.",
        }
    )

    return actions
