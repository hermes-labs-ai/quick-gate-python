from __future__ import annotations

import json
from pathlib import Path

from pygate.models import Finding, GateName, Severity

LONGREPR_MAX = 500


def resolve_pytest_command(commands_config: dict, cwd: Path, *, artifact_dir: Path | None = None) -> str:
    if "test" in commands_config:
        return commands_config["test"]
    if artifact_dir is None:
        return "pytest -q"
    report_path = artifact_dir / "pytest-report.json"
    import shlex

    return f"pytest --json-report --json-report-file={shlex.quote(str(report_path))} -q"


def parse_pytest_output(
    stdout: str,
    stderr: str,
    exit_code: int,
    report_path: Path | None,
    cwd: Path,
) -> list[Finding]:
    if report_path and report_path.exists():
        return _parse_json_report(report_path, exit_code, cwd)
    return []


def _parse_json_report(report_path: Path, exit_code: int, cwd: Path) -> list[Finding]:
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return []

    if not isinstance(data, dict):
        return []

    tests = data.get("tests", [])
    findings: list[Finding] = []

    for test in tests:
        outcome = test.get("outcome", "")
        if outcome not in ("failed", "error"):
            continue

        nodeid = test.get("nodeid", "")
        call = test.get("call", {})
        longrepr = call.get("longrepr", "")
        duration = call.get("duration", 0)

        # Extract file path from nodeid (e.g., "tests/test_foo.py::test_bar")
        file_part = nodeid.split("::")[0] if "::" in nodeid else nodeid

        # Sanitize nodeid for use as finding id
        safe_id = nodeid.replace("::", "_").replace("/", "_").replace(".", "_")
        finding_id = f"pytest_{safe_id}"

        # Truncate longrepr
        truncated = longrepr[:LONGREPR_MAX] + "..." if len(longrepr) > LONGREPR_MAX else longrepr

        # Short summary from first line of longrepr or just the nodeid
        first_line = longrepr.split("\n")[0][:200] if longrepr else ""
        summary = f"{nodeid}: {first_line}" if first_line else f"{nodeid} failed"

        findings.append(
            Finding(
                id=finding_id,
                gate=GateName.TEST,
                severity=Severity.HIGH,
                summary=summary,
                files=[file_part] if file_part else [],
                actual="failed",
                threshold="passed",
                raw={
                    "longrepr": truncated,
                    "duration": duration,
                    "outcome": outcome,
                },
            )
        )

    return findings
