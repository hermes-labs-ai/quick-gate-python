from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pygate.api import _evaluate
from pygate.config import load_config
from pygate.constants import FAILURES_FILE, GATE_RESULT_FILE, PYGATE_DIR, RUN_METADATA_FILE
from pygate.env import capture_environment
from pygate.exec import run_command
from pygate.fs import ensure_dir, now_iso, write_json
from pygate.models import Confidence, FailuresPayload, InferredHint, RunMetadata, RunMode, RunStatus


def _git_info(cwd: Path) -> dict[str, str | None]:
    from pygate.env import command_exists

    if not command_exists("git"):
        return {"repo": None, "branch": None}

    repo = None
    branch = None
    trace = run_command(["git", "config", "--get", "remote.origin.url"], cwd=cwd, timeout_seconds=10)
    if trace.exit_code == 0:
        repo = trace.stdout.strip() or None
    trace = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, timeout_seconds=10)
    if trace.exit_code == 0:
        branch = trace.stdout.strip() or None
    return {"repo": repo, "branch": branch}


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"run_{ts}_{short_uuid}"


def execute_run(
    *,
    mode: RunMode,
    changed_files: list[str],
    cwd: Path | None = None,
    output_dir: Path | None = None,
    unsafe_shell: bool = False,
) -> dict[str, Any]:
    """Run gates and write legacy artifacts to the explicitly selected dir.

    The default remains ``cwd/.pygate`` for callers of this legacy artifact
    writer. Embedders should use :func:`pygate.api.evaluate`, which writes
    nothing.
    """

    cwd = cwd or Path.cwd()
    artifact_dir = output_dir or cwd / PYGATE_DIR
    if not artifact_dir.is_absolute():
        artifact_dir = cwd / artifact_dir
    artifact_dir = artifact_dir.resolve()
    ensure_dir(artifact_dir)
    run_id = _generate_run_id()
    started_at = now_iso()
    start_ms = _monotonic_ms()
    config = load_config(cwd)
    environment = capture_environment()
    evaluation = _evaluate(
        mode=mode,
        checked_paths=changed_files,
        cwd=cwd,
        config=config,
        unsafe_shell=unsafe_shell,
        artifact_dir=artifact_dir,
    )
    result = evaluation.result
    status = RunStatus.PASS if result.status == "pass" else RunStatus.FAIL
    git = _git_info(cwd)
    inferred_hints = [
        InferredHint(
            finding_id=f.id,
            hint=(
                f"Start with the deterministic gate failure in {f.gate.value}. "
                "Inspect command output in run-metadata traces."
            ),
            confidence=Confidence.LOW,
        )
        for f in evaluation.findings
    ]
    failures = FailuresPayload(
        run_id=run_id,
        mode=mode,
        status=status,
        timestamp=now_iso(),
        repo=git["repo"],
        branch=git["branch"],
        changed_files=changed_files,
        gates=evaluation.gate_results,
        findings=evaluation.findings,
        inferred_hints=inferred_hints,
    )
    metadata = RunMetadata(
        run_id=run_id,
        mode=mode,
        started_at=started_at,
        completed_at=now_iso(),
        duration_ms=_monotonic_ms() - start_ms,
        config_source=config.get("source", "defaults"),
        environment=environment,
        command_traces=evaluation.traces,
    )
    failures_path = artifact_dir / Path(FAILURES_FILE).name
    metadata_path = artifact_dir / Path(RUN_METADATA_FILE).name
    gate_result_path = artifact_dir / GATE_RESULT_FILE
    write_json(failures_path, failures.model_dump(mode="json"))
    write_json(metadata_path, metadata.model_dump(mode="json"))
    write_json(gate_result_path, result.model_dump(mode="json", by_alias=True))
    return {
        "status": status.value,
        "failures_path": str(failures_path),
        "metadata_path": str(metadata_path),
        "gate_result_path": str(gate_result_path),
        "run_id": run_id,
    }


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)
