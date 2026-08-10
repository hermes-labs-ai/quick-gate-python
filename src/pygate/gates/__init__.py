from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from pygate.exec import run_command
from pygate.gates.pyright import parse_pyright_output, resolve_pyright_command
from pygate.gates.pytest_gate import parse_pytest_output, resolve_pytest_command
from pygate.gates.ruff import parse_ruff_output, resolve_ruff_command
from pygate.models import (
    CommandTrace,
    Finding,
    GateName,
    GateResult,
    GateStatus,
    RunMode,
    Severity,
)


def _finding_for_exit_code(gate: GateName, trace: CommandTrace) -> Finding:
    exit_code = trace.exit_code if trace.exit_code is not None else 1
    return Finding(
        id=f"{gate.value}_exit_{exit_code}",
        gate=gate,
        severity=Severity.HIGH,
        summary=f"{gate.value} command failed with exit code {exit_code}",
        actual=exit_code,
        threshold=0,
        raw={
            "command": trace.command,
            "stderr_excerpt": "\n".join(trace.stderr.splitlines()[:30]),
            "stdout_excerpt": "\n".join(trace.stdout.splitlines()[:30]),
        },
    )


def run_deterministic_gates(
    *,
    mode: RunMode,
    cwd: Path,
    config: dict,
    changed_files: list[str],
    timeout_seconds: float | None = None,
    output_cap_bytes: int = 1_048_576,
    unsafe_shell: bool = False,
    artifact_dir: Path | None = None,
) -> tuple[list[GateResult], list[Finding], list[CommandTrace]]:
    gates_config = config.get("gates", {})
    commands_config = config.get("commands", {})
    test_in_canary = gates_config.get("test_in_canary", False)

    gate_plan = [
        (GateName.LINT, True),
        (GateName.TYPECHECK, True),
        (GateName.TEST, mode == RunMode.FULL or test_in_canary),
    ]

    gate_results: list[GateResult] = []
    all_findings: list[Finding] = []
    all_traces: list[CommandTrace] = []

    for gate_name, enabled in gate_plan:
        if not enabled:
            gate_results.append(GateResult(name=gate_name, status=GateStatus.SKIPPED, duration_ms=0))
            continue

        cmd = _resolve_command(gate_name, commands_config, cwd, artifact_dir=artifact_dir)
        gate_deadline = time.monotonic() + float(
            config.get("policy", {}).get("gate_timeout_seconds", timeout_seconds or 600)
        )
        remaining = max(0.01, gate_deadline - time.monotonic())
        command_deadline = min(timeout_seconds, remaining) if timeout_seconds is not None else remaining
        trace = run_command(
            cmd,
            cwd=cwd,
            timeout_seconds=command_deadline,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            shell=unsafe_shell,
            output_cap_bytes=output_cap_bytes,
        )
        all_traces.append(trace)

        if trace.exit_code != 0:
            findings = _parse_gate_output(gate_name, trace, cwd, artifact_dir=artifact_dir)
            if not findings:
                findings = [_finding_for_exit_code(gate_name, trace)]
            all_findings.extend(findings)
            gate_results.append(GateResult(name=gate_name, status=GateStatus.FAIL, duration_ms=trace.duration_ms))
        else:
            gate_results.append(GateResult(name=gate_name, status=GateStatus.PASS, duration_ms=trace.duration_ms))

    return gate_results, all_findings, all_traces


def _resolve_command(
    gate: GateName,
    commands_config: dict,
    cwd: Path,
    *,
    artifact_dir: Path | None,
) -> str | Sequence[str]:
    if gate.value in commands_config:
        return commands_config[gate.value]

    match gate:
        case GateName.LINT:
            return resolve_ruff_command(commands_config)
        case GateName.TYPECHECK:
            return resolve_pyright_command(commands_config)
        case GateName.TEST:
            return resolve_pytest_command(commands_config, cwd, artifact_dir=artifact_dir)
        case _:
            raise ValueError(f"Unknown gate: {gate}")


def _parse_gate_output(gate: GateName, trace: CommandTrace, cwd: Path, *, artifact_dir: Path | None) -> list[Finding]:
    match gate:
        case GateName.LINT:
            return parse_ruff_output(trace.stdout, trace.stderr, trace.exit_code or 1, cwd)
        case GateName.TYPECHECK:
            return parse_pyright_output(trace.stdout, trace.stderr, trace.exit_code or 1, cwd)
        case GateName.TEST:
            report_path = (artifact_dir or cwd / ".pygate") / "pytest-report.json"
            return parse_pytest_output(trace.stdout, trace.stderr, trace.exit_code or 1, report_path, cwd)
        case _:
            return []
