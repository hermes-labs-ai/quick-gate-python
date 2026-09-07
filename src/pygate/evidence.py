"""
pygate/evidence.py

Emits a `pygate run` evaluation as a Hermes Reliability Lab result envelope
(`hermes.reliability-lab.result/1`): tool, version, status, input hash,
findings, exit code, timestamp, optional Git SHA — with the ordinary
`GateResultV1` (the `gate-result/v1` contract shared with HermesGate and
QuickGate.js) embedded verbatim.

This module changes no detection, no gate resolution, and no scoring. It
restates the existing CLI contract in a shared shape: gate-result status
"pass" -> lab "pass"; a check that could not run ("missing" executable, or
"error") -> lab "unknown" for that check, because a check that did not run is
not a check that passed; a check that ran and failed, or timed out, -> lab
"fail". The overall envelope status is the worst of those per-check findings
plus the individual lint/typecheck/test findings pygate already produces.

    python -m pygate.evidence --mode canary
    python -m pygate.evidence --mode full --path fixtures/lab/broken

Added in v0.3.0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pygate import __version__
from pygate.api import evaluate
from pygate.models import RunMode

ENVELOPE = "hermes.reliability-lab.result/1"
TOOL = "pygate"

#: Ordered worst-last; the run's status is the worst finding it carries.
STATUS_ORDER = ("pass", "warn", "unknown", "fail")

#: gate-result/v1 top-level `status` -> lab status. "pass" is the only value
#: that does not block; everything else stops a CI gate, so it maps to "fail"
#: at the envelope level even though individual checks may be "unknown".
RESULT_STATUS = {"pass": "pass", "fail": "fail", "timeout": "fail", "error": "fail"}

#: gate-result/v1 per-check `status` -> lab severity. A check that did not run
#: ("missing" executable, or "error" starting it) is unknown, not a pass and
#: not a code-quality failure.
CHECK_SEVERITY = {
    "pass": "pass",
    "fail": "fail",
    "timeout": "fail",
    "missing": "unknown",
    "error": "unknown",
}

#: pygate Finding.severity (low/medium/high/critical) -> lab severity.
FINDING_SEVERITY = {"low": "warn", "medium": "warn", "high": "fail", "critical": "fail"}


# ---------------------------------------------------------------------------
# Envelope primitives (mirrors rule_audit/evidence.py; a narrow, product-owned
# adapter per product, not a shared SDK)
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def input_hash(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def finding(
    identifier: str, severity: str, summary: str, detail: str | None = None, path: str | None = None
) -> dict[str, Any]:
    if severity not in STATUS_ORDER:
        raise ValueError(f"unknown severity: {severity}")
    result: dict[str, Any] = {"id": identifier, "severity": severity, "summary": summary}
    if detail is not None:
        result["detail"] = detail
    if path is not None:
        result["path"] = path
    return result


def worst_status(findings: list[dict[str, Any]]) -> str:
    status = "pass"
    for item in findings:
        if STATUS_ORDER.index(item["severity"]) > STATUS_ORDER.index(status):
            status = item["severity"]
    return status


def _git(start: Path, *arguments: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(start), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_sha(start: Path) -> str | None:
    """Best-effort commit of the checkout the tool runs from, "-dirty" if unclean, else None."""
    head = _git(start, "rev-parse", "HEAD")
    if head is None or head.returncode or not head.stdout.strip():
        return None
    sha = head.stdout.strip()
    status = _git(start, "status", "--porcelain")
    if status is None or status.returncode:
        return sha
    return f"{sha}-dirty" if status.stdout.strip() else sha


def _timestamp(now: datetime | None = None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# From a GateResultV1 to findings
# ---------------------------------------------------------------------------


def findings_for(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One finding per check pygate ran, plus one per lint/typecheck/test finding.

    Native results are never renamed or dropped: a check's `argv`, `exit_code`,
    and stderr excerpt travel into the finding detail unchanged, and every
    entry in `result["findings"]` becomes its own lab finding.
    """
    findings: list[dict[str, Any]] = [
        finding(
            "gate.status",
            RESULT_STATUS.get(result["status"], "fail"),
            f"Overall gate result: {result['status']}.",
            f"schema {result['schema']}; {len(result['checks'])} check(s) ran.",
        )
    ]

    for check in result["checks"]:
        severity = CHECK_SEVERITY.get(check["status"], "unknown")
        if severity == "pass":
            continue  # a passing check is folded into gate.status; no extra noise
        argv = " ".join(check.get("argv") or [])
        detail_lines = [f"argv: {argv}"] if argv else []
        if check.get("exit_code") is not None:
            detail_lines.append(f"exit_code: {check['exit_code']}")
        stderr_excerpt = (check.get("stderr") or "").strip().splitlines()[:5]
        if stderr_excerpt:
            detail_lines.append("stderr: " + " / ".join(stderr_excerpt))
        findings.append(
            finding(
                f"check.{check['name']}.{check['status']}",
                severity,
                f"{check['name']}: {check['status']}"
                + (f" (exit {check['exit_code']})" if check.get("exit_code") is not None else ""),
                "\n".join(detail_lines) or None,
            )
        )

    for index, item in enumerate(result["findings"]):
        location = ""
        if item.get("files"):
            location = item["files"][0]
            if item.get("line") is not None:
                location += f":{item['line']}"
                if item.get("column") is not None:
                    location += f":{item['column']}"
        findings.append(
            finding(
                f"finding.{item.get('gate', 'unknown')}.{index}",
                FINDING_SEVERITY.get(item.get("severity"), "warn"),
                item.get("summary", ""),
                f"rule: {item['rule']}" if item.get("rule") else None,
                location or None,
            )
        )

    return findings


def _envelope(
    command: str, findings: list[dict[str, Any]], inputs: Any, exit_code: int, data: Any, timestamp: str
) -> dict[str, Any]:
    return {
        "envelope": ENVELOPE,
        "tool": TOOL,
        "toolVersion": __version__,
        "command": command,
        # A real evaluation over real files, not a simulation.
        "mode": "executed",
        "status": worst_status(findings),
        "inputHash": input_hash(inputs),
        "findings": findings,
        "exitCode": exit_code,
        "timestamp": timestamp,
        "gitSha": git_sha(Path(__file__).resolve().parent),
        "data": data,
    }


def envelope_for(*, mode: str, cwd: Path) -> dict[str, Any]:
    """Run `pygate.api.evaluate()` against `cwd` and return the run as an envelope.

    Writes nothing: `evaluate()` is the same side-effect-free entry point
    `pygate run` uses without `--output-dir`.
    """
    result = evaluate(mode=RunMode(mode), checked_paths=["."], cwd=cwd)
    data = result.model_dump(mode="json", by_alias=True)
    findings = findings_for(data)
    exit_code = 0 if data["status"] == "pass" else 1
    return _envelope(
        "run",
        findings,
        {"command": "run", "mode": mode, "cwd": str(cwd)},
        exit_code,
        {"mode": mode, "cwd": str(cwd), "effects": {"writes": "none", "network": "none"}, "result": data},
        _timestamp(),
    )


def input_error_envelope(identifier: str, message: str, mode: str, cwd: str) -> dict[str, Any]:
    """The run could not start; say so in the same shape rather than only on stderr."""
    findings = [finding(identifier, "unknown", message, "No gates ran, so nothing is known about this project.")]
    return _envelope(
        "run",
        findings,
        {"command": "run", "mode": mode, "cwd": cwd},
        1,
        {"mode": mode, "cwd": cwd, "effects": {"writes": "none", "network": "none"}, "result": None},
        _timestamp(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pygate.evidence",
        description="Run pygate and print the result as a Reliability Lab envelope.",
    )
    parser.add_argument("--mode", required=True, choices=["canary", "full"])
    parser.add_argument("--path", default=".", help="Project directory to evaluate (default: cwd).")
    args = parser.parse_args(argv)

    cwd = Path(args.path).resolve()
    if not cwd.is_dir():
        result = input_error_envelope(
            "input.not-a-directory", f"{args.path!r} is not a directory.", args.mode, str(cwd)
        )
    elif not (cwd / "pyproject.toml").exists() and not (cwd / "pygate.toml").exists():
        result = input_error_envelope(
            "input.no-config",
            f"No pyproject.toml or pygate.toml in {cwd}; pygate has nothing to configure gates from.",
            args.mode,
            str(cwd),
        )
    else:
        result = envelope_for(mode=args.mode, cwd=cwd)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result["exitCode"]


if __name__ == "__main__":
    sys.exit(main())
