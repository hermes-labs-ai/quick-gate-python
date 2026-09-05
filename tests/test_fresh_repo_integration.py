"""Fresh-repository proof: pygate against real subprocesses, not mocked tool output.

Unlike the rest of the suite (mocked Ruff/Pyright/pytest output per AGENTS.md), these
tests build throwaway project directories on disk and invoke the installed `pygate`
console script for real. They are the same fixtures the root action's CI smoke test
(`.github/workflows/action-smoke.yml`) exercises on GitHub-hosted runners, reproduced
here so a maintainer or adopter can verify the pass/fail/escalated contract locally and
offline with one command.

Excluded from the default `pytest` run (see `[tool.pytest.ini_options] addopts` in
pyproject.toml) because they require `ruff`, `pyright`, and `pygate` itself on PATH.
Run explicitly with:

    pytest -m integration
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "action-fixture"

PYGATE = shutil.which("pygate")
RUFF = shutil.which("ruff")
PYRIGHT = shutil.which("pyright")

requires_tools = pytest.mark.skipif(
    not (PYGATE and RUFF and PYRIGHT),
    reason="pygate, ruff, and pyright must all be installed on PATH for fresh-repository proof",
)


def _build_project(tmp_path: Path, *, pyproject: str, check_source: str) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    shutil.copy(FIXTURE_DIR / pyproject, project / "pyproject.toml")
    shutil.copy(FIXTURE_DIR / check_source, project / "check.py")
    return project


def _run_pygate(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    assert PYGATE is not None
    return subprocess.run(
        [PYGATE, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


@requires_tools
def test_fresh_repository_with_no_issues_passes(tmp_path: Path) -> None:
    project = _build_project(tmp_path, pyproject="pyproject.toml", check_source="pass.py")

    result = _run_pygate("run", "--mode", "canary", cwd=project)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "gate-result/v1"
    assert payload["status"] == "pass"


@requires_tools
def test_fresh_repository_with_a_type_error_fails_and_escalates(tmp_path: Path) -> None:
    project = _build_project(tmp_path, pyproject="pyproject.toml", check_source="fail.py")

    run_result = _run_pygate("run", "--mode", "canary", "--output-dir", ".pygate", cwd=project)

    assert run_result.returncode == 1
    assert json.loads(run_result.stdout)["status"] == "fail"

    failures_path = project / ".pygate" / "failures.json"
    assert failures_path.exists()
    failures = json.loads(failures_path.read_text())
    assert any(f["gate"] == "typecheck" for f in failures["findings"])

    repair_result = _run_pygate("repair", "--input", str(failures_path), cwd=project)

    assert repair_result.returncode == 2, repair_result.stderr
    escalation = json.loads(repair_result.stdout)
    assert escalation["status"] == "escalated"
    assert (project / ".pygate" / "escalation.json").exists()


@requires_tools
def test_fresh_repository_with_a_ruff_fixable_issue_repairs_to_pass(tmp_path: Path) -> None:
    project = _build_project(tmp_path, pyproject="repair-pyproject.toml", check_source="repair.py")

    run_result = _run_pygate("run", "--mode", "canary", "--output-dir", ".pygate", cwd=project)

    assert run_result.returncode == 1
    assert json.loads(run_result.stdout)["status"] == "fail"

    failures_path = project / ".pygate" / "failures.json"
    failures = json.loads(failures_path.read_text())
    assert any(f["gate"] == "lint" for f in failures["findings"])

    repair_result = _run_pygate("repair", "--input", str(failures_path), cwd=project)

    assert repair_result.returncode == 0, repair_result.stderr
    report = json.loads(repair_result.stdout)
    assert report["status"] == "pass"
    assert (project / ".pygate" / "repair-report.json").exists()

    # Re-running the gate proves the repaired file is durably clean, not just
    # reported clean by the repair loop's own bookkeeping.
    verify_result = _run_pygate("run", "--mode", "canary", cwd=project)
    assert verify_result.returncode == 0
    assert json.loads(verify_result.stdout)["status"] == "pass"
