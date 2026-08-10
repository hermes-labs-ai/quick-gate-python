from __future__ import annotations

import shutil
import time
from pathlib import Path

from pygate.config import load_config
from pygate.constants import (
    ESCALATION_FILE,
    FAILURES_FILE,
    PYGATE_DIR,
    REPAIR_REPORT_FILE,
    EscalationCode,
)
from pygate.deterministic_fix import run_deterministic_prefix
from pygate.env import command_exists
from pygate.exec import run_command
from pygate.fs import ensure_dir, read_json, write_json
from pygate.models import (
    Escalation,
    FailuresPayload,
    RepairAttempt,
    RepairReport,
)
from pygate.run_command import execute_run
from pygate.summarize_command import execute_summarize

_BACKUP_EXCLUDES = {".pygate", ".git", "__pycache__", ".venv", ".tox", ".nox", "dist", "node_modules"}


def _backup_workspace(cwd: Path, backup_dir: Path) -> None:
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(cwd, backup_dir, symlinks=True, ignore=shutil.ignore_patterns(*_BACKUP_EXCLUDES))


def _restore_workspace(cwd: Path, backup_dir: Path) -> None:
    for item in cwd.iterdir():
        if item.name in _BACKUP_EXCLUDES:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in backup_dir.iterdir():
        dest = cwd / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def _diff_snapshot(cwd: Path) -> dict[str, int]:
    if not command_exists("git"):
        return {}
    trace = run_command(
        ["git", "diff", "--numstat", "--", ".", ":(exclude).pygate", ":(exclude)__pycache__", ":(exclude).venv"],
        cwd=cwd,
    )
    if trace.exit_code != 0:
        return {}
    result: dict[str, int] = {}
    for line in trace.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added = int(parts[0]) if parts[0] != "-" else 0
            removed = int(parts[1]) if parts[1] != "-" else 0
            result[parts[2]] = added + removed
    return result


def _compute_patch_lines(before: dict[str, int], after: dict[str, int]) -> int:
    all_files = set(before) | set(after)
    total = 0
    for f in all_files:
        total += abs(after.get(f, 0) - before.get(f, 0))
    return total


def _escalate(reason_code: str, message: str, evidence: dict, cwd: Path) -> dict:
    escalation = Escalation(
        reason_code=reason_code,
        message=message,
        evidence=evidence,
    )
    write_json(cwd / ESCALATION_FILE, escalation.model_dump(mode="json"))
    return escalation.model_dump(mode="json")


def execute_repair(
    *,
    input_path: str,
    max_attempts: int | None = None,
    cwd: Path | None = None,
) -> dict:
    cwd = cwd or Path.cwd()
    pygate_dir = cwd / PYGATE_DIR
    ensure_dir(pygate_dir)

    config = load_config(cwd)
    policy = config.get("policy", {})
    max_attempts = max_attempts if max_attempts is not None else policy.get("max_attempts", 3)
    max_patch_lines = policy.get("max_patch_lines", 150)
    abort_threshold = policy.get("abort_on_no_improvement", 2)
    time_cap_seconds = policy.get("time_cap_seconds", 1200)

    failures_data = read_json(Path(input_path))
    failures = FailuresPayload(**failures_data)

    previous_count = len(failures.findings)
    no_improvement = 0
    attempts: list[RepairAttempt] = []
    started = time.monotonic()

    # Detect mode from failures for re-runs
    mode = failures.mode

    for attempt_num in range(1, max_attempts + 1):
        # Time cap check
        elapsed = time.monotonic() - started
        if elapsed > time_cap_seconds:
            return _escalate(
                EscalationCode.UNKNOWN_BLOCKER,
                f"Time cap reached ({time_cap_seconds}s).",
                {"elapsed_seconds": int(elapsed)},
                cwd,
            )

        # Backup
        backup_dir = pygate_dir / f"backup-attempt-{attempt_num}"
        _backup_workspace(cwd, backup_dir)

        # Snapshot before
        before_snap = _diff_snapshot(cwd)

        # Run deterministic fixes
        actions = run_deterministic_prefix(cwd=cwd, failures=failures)

        # If no fix strategies applied, don't waste attempts
        if not actions and attempt_num > 1:
            return _escalate(
                EscalationCode.NO_IMPROVEMENT,
                f"No applicable fix strategies for remaining {previous_count} finding(s).",
                {
                    "attempts": [a.model_dump(mode="json") for a in attempts],
                    "latest_failures_path": str(cwd / FAILURES_FILE),
                    "remaining_gates": list({f.gate.value for f in failures.findings}),
                },
                cwd,
            )

        # Snapshot after
        after_snap = _diff_snapshot(cwd)
        patch_lines = _compute_patch_lines(before_snap, after_snap)

        # Patch budget check
        if patch_lines > max_patch_lines:
            _restore_workspace(cwd, backup_dir)
            return _escalate(
                EscalationCode.PATCH_BUDGET_EXCEEDED,
                f"Patch exceeded budget: {patch_lines} lines > {max_patch_lines} max.",
                {
                    "attempt": attempt_num,
                    "patch_lines": patch_lines,
                    "max_patch_lines": max_patch_lines,
                },
                cwd,
            )

        # Re-run gates and regenerate agent brief
        rerun = execute_run(mode=mode, changed_files=failures.changed_files, cwd=cwd)
        execute_summarize(input_path=rerun["failures_path"], cwd=cwd)
        rerun_failures_data = read_json(Path(rerun["failures_path"]))
        rerun_failures = FailuresPayload(**rerun_failures_data)
        current_count = len(rerun_failures.findings)

        improved = current_count < previous_count
        worsened = current_count > previous_count

        attempts.append(
            RepairAttempt(
                attempt=attempt_num,
                patch_lines=patch_lines,
                before_findings=previous_count,
                after_findings=current_count,
                improved=improved,
                worsened=worsened,
                status=rerun["status"],
                actions=list(actions),
            )
        )

        # Pass check
        if rerun["status"] == "pass":
            report = RepairReport(status="pass", attempts=attempts)
            write_json(cwd / REPAIR_REPORT_FILE, report.model_dump(mode="json"))
            return report.model_dump(mode="json")

        # Rollback if worsened
        if worsened:
            _restore_workspace(cwd, backup_dir)
            # Don't update previous_count or failures — workspace was restored
        else:
            previous_count = current_count
            failures = rerun_failures

        # Track improvement
        if improved:
            no_improvement = 0
        else:
            no_improvement += 1

        # No improvement abort
        if no_improvement >= abort_threshold:
            return _escalate(
                EscalationCode.NO_IMPROVEMENT,
                f"No measurable improvement for {no_improvement} consecutive attempt(s).",
                {
                    "attempts": [a.model_dump(mode="json") for a in attempts],
                    "latest_failures_path": str(cwd / FAILURES_FILE),
                },
                cwd,
            )

    # Attempts exhausted
    return _escalate(
        EscalationCode.UNKNOWN_BLOCKER,
        f"Attempts exhausted ({max_attempts}).",
        {"latest_failures_path": str(cwd / FAILURES_FILE)},
        cwd,
    )
