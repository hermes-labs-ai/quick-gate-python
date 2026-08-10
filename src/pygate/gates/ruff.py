from __future__ import annotations

import json
from pathlib import Path

from pygate.models import Finding, GateName, Severity


def resolve_ruff_command(commands_config: dict) -> str:
    return commands_config.get("lint", "ruff check --no-cache --output-format json --exclude .pygate .")


def _severity_for_code(code: str) -> Severity:
    if not code:
        return Severity.MEDIUM
    prefix = code[0].upper()
    if prefix in ("E", "F"):
        return Severity.HIGH
    if prefix == "W":
        return Severity.MEDIUM
    return Severity.MEDIUM


def parse_ruff_output(stdout: str, stderr: str, exit_code: int, cwd: Path) -> list[Finding]:
    try:
        violations = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(violations, list):
        return []

    findings: list[Finding] = []
    for v in violations:
        code = v.get("code", "")
        filename = v.get("filename", "")
        location = v.get("location", {})
        row = location.get("row", 0)
        col = location.get("column", 0)
        message = v.get("message", "")
        fix_info = v.get("fix") or {}

        # Relativize filename
        try:
            rel_path = str(Path(filename).relative_to(cwd))
        except ValueError:
            rel_path = filename

        idx = len(findings)
        finding_id = f"ruff_{code}_{rel_path}_{row}_{idx}"

        findings.append(
            Finding(
                id=finding_id,
                gate=GateName.LINT,
                severity=_severity_for_code(code),
                summary=f"{code}: {message}",
                files=[rel_path],
                rule=code,
                line=row,
                column=col,
                actual=exit_code,
                threshold=0,
                raw={
                    "fix_applicability": fix_info.get("applicability"),
                    "url": v.get("url"),
                },
            )
        )

    return findings
