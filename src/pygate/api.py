from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pygate import __version__
from pygate.config import load_config
from pygate.contract import CheckResult, GateResultV1
from pygate.exec import run_command
from pygate.gates import run_deterministic_gates
from pygate.models import CommandTrace, Finding, GateResult, RunMode
from pygate.snapshot import config_digest, snapshot_digest


@dataclass(frozen=True)
class Evaluation:
    result: GateResultV1
    gate_results: list[GateResult]
    findings: list[Finding]
    traces: list[CommandTrace]
    config: dict[str, Any]


def _command_version(argv: list[str], *, cwd: Path, timeout_seconds: float, output_cap_bytes: int) -> str:
    if not argv:
        return ""
    trace = run_command(
        [argv[0], "--version"],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        output_cap_bytes=output_cap_bytes,
    )
    version = (trace.stdout or trace.stderr).strip().splitlines()
    if version:
        return version[0][:500]
    return "unavailable"


def _check_status(trace: CommandTrace) -> Literal["pass", "fail", "timeout", "missing", "error"]:
    if trace.timed_out:
        return "timeout"
    if trace.missing_executable:
        return "missing"
    if trace.error:
        return "error"
    return "pass" if trace.exit_code == 0 else "fail"


def _config_identity(config: dict[str, Any]) -> str:
    source = str(config.get("source", "defaults"))
    if source == "defaults":
        return source
    return Path(source).name


def _evaluate(
    *,
    mode: RunMode,
    checked_paths: list[str],
    cwd: Path,
    config: dict[str, Any] | None,
    unsafe_shell: bool,
    artifact_dir: Path | None,
) -> Evaluation:
    start = time.monotonic()
    loaded_config = config if config is not None else load_config(cwd)
    policy = loaded_config.get("policy", {})
    command_timeout = float(policy.get("command_timeout_seconds", 120))
    output_cap = int(policy.get("output_cap_bytes", 1_048_576))
    snapshot_before, canonical_paths = snapshot_digest(checked_paths, cwd=cwd)
    gate_results, findings, traces = run_deterministic_gates(
        mode=mode,
        cwd=cwd,
        config=loaded_config,
        changed_files=checked_paths,
        timeout_seconds=command_timeout,
        output_cap_bytes=output_cap,
        unsafe_shell=unsafe_shell or bool(loaded_config.get("allow_unsafe_shell", False)),
        artifact_dir=artifact_dir,
    )
    snapshot_after, _ = snapshot_digest(checked_paths, cwd=cwd)
    errors: list[str | dict[str, Any]] = []
    diagnostics: list[str | dict[str, Any]] = []
    if snapshot_before != snapshot_after:
        errors.append("checked input changed while the gate was running")
        diagnostics.append("snapshot digest mismatch: result is stale and must not be treated as a clean read")
    for trace in traces:
        diagnostics.extend(trace.diagnostics)
        if trace.error:
            errors.append(trace.error)

    command_versions: dict[str, str | dict[str, Any]] = {}
    for trace in traces:
        if trace.argv:
            key = trace.argv[0]
            command_versions.setdefault(
                key,
                _command_version(
                    trace.argv,
                    cwd=cwd,
                    timeout_seconds=min(command_timeout, 10),
                    output_cap_bytes=output_cap,
                ),
            )
    checks = [
        CheckResult(
            name=gate.name.value,
            status=_check_status(trace),
            argv=trace.argv,
            elapsed_ms=trace.duration_ms,
            exit_code=trace.exit_code,
            signal=trace.signal,
            timed_out=trace.timed_out,
            output_truncated=trace.output_truncated,
            stdout=trace.stdout,
            stderr=trace.stderr,
            diagnostics=trace.diagnostics,
        )
        for gate, trace in zip((g for g in gate_results if g.status.value != "skipped"), traces, strict=False)
    ]
    output_truncated = any(trace.output_truncated for trace in traces)
    timed_out = any(trace.timed_out for trace in traces)
    status = "pass" if not findings and not errors and not timed_out else "timeout" if timed_out else "fail"
    result = GateResultV1(
        status=status,
        snapshot_digest=snapshot_before,
        snapshot_digest_after=snapshot_after,
        snapshot_changed=snapshot_before != snapshot_after,
        checked_paths=canonical_paths,
        checks=checks,
        findings=[finding.model_dump(mode="json") for finding in findings],
        command_versions=command_versions,
        elapsed_ms=int((time.monotonic() - start) * 1000),
        output_truncated=output_truncated,
        errors=errors,
        diagnostics=diagnostics,
        config_identity=_config_identity(loaded_config),
        config_digest=config_digest(loaded_config),
        config_version=str(loaded_config.get("config_version", "pygate-config/v1")),
        package_version=__version__,
    )
    return Evaluation(result, gate_results, findings, traces, loaded_config)


def evaluate(
    *,
    mode: RunMode,
    checked_paths: list[str] | None = None,
    cwd: Path | None = None,
    config: dict[str, Any] | None = None,
    unsafe_shell: bool = False,
) -> GateResultV1:
    """Evaluate gates without writing files, changing env, or creating state."""

    return _evaluate(
        mode=mode,
        checked_paths=checked_paths or [],
        cwd=cwd or Path.cwd(),
        config=config,
        unsafe_shell=unsafe_shell,
        artifact_dir=None,
    ).result
