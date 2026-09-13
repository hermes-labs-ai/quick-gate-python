"""Render a deliberately small, safe GitHub Actions job summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pygate import __version__

_ACTION_NAME = "PyGate Quality Gates"
_SOURCE_URL = "https://github.com/hermes-labs-ai/quick-gate-python"
_MAX_FAILURES_BYTES = 1_000_000
_FINAL_STATUSES = frozenset({"pass", "fail", "escalated"})
_REPAIR_STATUSES = frozenset({"pass", "fail", "escalated", "skipped"})
_CHECK_NAMES = frozenset({"lint", "typecheck", "test"})
_CHECK_STATUSES = frozenset({"pass", "fail", "skipped"})


def _safe_status(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else "unavailable"


def _check_counts(path: Path) -> str:
    """Count only recognized gate states from a bounded artifact read."""

    try:
        if path.stat().st_size > _MAX_FAILURES_BYTES:
            return "unavailable"
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unavailable"

    gates = payload.get("gates") if isinstance(payload, dict) else None
    if not isinstance(gates, list):
        return "unavailable"

    statuses: dict[str, str] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        name = gate.get("name")
        status = gate.get("status")
        if name in _CHECK_NAMES and status in _CHECK_STATUSES and name not in statuses:
            statuses[name] = status

    return (
        ", ".join(
            f"{status}: {sum(1 for value in statuses.values() if value == status)}"
            for status in ("pass", "fail", "skipped")
        )
        + f" (total: {len(statuses)})"
    )


def render_summary(*, status: str, repair_status: str, failures_path: Path) -> str:
    """Return fixed Markdown whose dynamic values are allow-listed counts and states."""

    safe_status = _safe_status(status, _FINAL_STATUSES)
    safe_repair_status = _safe_status(repair_status, _REPAIR_STATUSES)
    return "\n".join(
        (
            f"## {_ACTION_NAME}",
            "",
            f"Status: {safe_status}",
            f"Checks: {_check_counts(failures_path)}",
            f"Repair: {safe_repair_status}",
            f"Version: {__version__}",
            f"Source: [PyGate action source]({_SOURCE_URL})",
            "",
        )
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render a safe PyGate Actions summary")
    parser.add_argument("--failures", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--repair-status", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    with Path(args.output).open("a", encoding="utf-8") as output:
        output.write(
            render_summary(
                status=args.status,
                repair_status=args.repair_status,
                failures_path=Path(args.failures),
            )
        )


if __name__ == "__main__":
    main()
