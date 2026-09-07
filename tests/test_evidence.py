"""Reliability Lab envelope contract for pygate."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pygate import __version__, evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures" / "lab"


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURES / name, dest)
    return dest


def test_clean_fixture_is_a_stable_pass_with_no_extra_findings(tmp_path):
    project = _copy_fixture("clean", tmp_path)
    result = evidence.envelope_for(mode="canary", cwd=project)
    again = evidence.envelope_for(mode="canary", cwd=project)

    assert result["envelope"] == "hermes.reliability-lab.result/1"
    assert result["tool"] == "pygate"
    assert result["toolVersion"] == __version__
    assert result["command"] == "run"
    assert result["mode"] == "executed"
    assert result["status"] == "pass" == evidence.worst_status(result["findings"])
    assert result["exitCode"] == 0
    assert [f["id"] for f in result["findings"]] == ["gate.status"]
    assert result["data"]["result"]["checks"][0]["status"] == "pass"
    assert json.loads(json.dumps(result)) == result

    for key in ("status", "exitCode"):
        assert result[key] == again[key]
    assert result["inputHash"].startswith("sha256:")


def test_broken_fixture_fails_on_typecheck_with_the_real_pyright_finding(tmp_path):
    project = _copy_fixture("broken", tmp_path)
    result = evidence.envelope_for(mode="canary", cwd=project)

    assert result["status"] == "fail"
    assert result["exitCode"] == 1
    ids = [f["id"] for f in result["findings"]]
    assert "check.typecheck.fail" in ids
    assert any(f_id.startswith("finding.typecheck.") for f_id in ids)
    typecheck_finding = next(f for f in result["findings"] if f["id"].startswith("finding.typecheck."))
    assert "reportReturnType" in typecheck_finding["summary"]
    assert typecheck_finding["severity"] == "fail"
    # lint stayed clean: no check.lint.* finding at all (a passing check adds nothing).
    assert not any(f_id.startswith("check.lint.") for f_id in ids)


def test_a_missing_native_tool_is_reported_as_unknown_not_as_a_failed_check(tmp_path):
    """Real PATH restriction, real pygate code path — not a fabricated finding."""
    project = _copy_fixture("clean", tmp_path)
    restricted = tmp_path / "bin"
    restricted.mkdir()
    for tool in ("python3", "pyright"):
        found = shutil.which(tool)
        if found:
            (restricted / tool).symlink_to(found)

    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(restricted)
    try:
        result = evidence.envelope_for(mode="canary", cwd=project)
    finally:
        os.environ["PATH"] = original_path

    ids = {f["id"]: f for f in result["findings"]}
    assert "check.lint.missing" in ids
    assert ids["check.lint.missing"]["severity"] == "unknown"
    assert "ruff" in ids["check.lint.missing"]["detail"]
    # The result still fails overall (a CI gate with a tool missing does not
    # silently pass), but the specific check is unknown, not a code defect.
    assert result["status"] == "fail"
    assert result["exitCode"] == 1


def test_findings_never_rename_or_drop_a_native_result():
    project_result = {
        "schema": "gate-result/v1",
        "status": "fail",
        "checks": [
            {"name": "lint", "status": "pass", "argv": ["ruff", "check", "."], "exit_code": 0},
            {"name": "typecheck", "status": "timeout", "argv": ["pyright", "."], "exit_code": None},
        ],
        "findings": [
            {"gate": "lint", "severity": "critical", "summary": "S001 unused import",
             "rule": "F401", "files": ["a.py"], "line": 3, "column": 1},
        ],
    }
    findings = evidence.findings_for(project_result)
    ids = [f["id"] for f in findings]
    assert ids == ["gate.status", "check.typecheck.timeout", "finding.lint.0"]
    assert findings[1]["severity"] == "fail"  # timeout blocks completion, same as fail
    assert findings[2]["path"] == "a.py:3:1"
    assert findings[2]["detail"] == "rule: F401"
    assert findings[2]["severity"] == "fail"  # critical -> fail, not silently downgraded


def test_input_errors_exit_1_with_an_unknown_envelope(tmp_path):
    result = evidence.main(["--mode", "canary", "--path", str(tmp_path / "missing-dir")])
    assert result == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    payload = json.loads(subprocess.run(
        [sys.executable, "-m", "pygate.evidence", "--mode", "canary", "--path", str(empty)],
        cwd=REPO_ROOT, env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        text=True, capture_output=True, timeout=30,
    ).stdout, strict=True)
    assert payload["status"] == "unknown"
    assert payload["exitCode"] == 1
    assert payload["findings"][0]["id"] == "input.no-config"
    assert payload["data"]["result"] is None


def test_overall_status_is_the_worst_finding_present():
    assert evidence.worst_status([]) == "pass"
    assert evidence.worst_status([evidence.finding("a", "warn", "x"),
                                  evidence.finding("b", "unknown", "y")]) == "unknown"
    assert evidence.worst_status([evidence.finding("a", "unknown", "x"),
                                  evidence.finding("b", "fail", "y")]) == "fail"
    with pytest.raises(ValueError):
        evidence.finding("a", "bad", "x")


def test_input_hash_is_stable_for_the_same_project_and_moves_with_mode(tmp_path):
    project = _copy_fixture("clean", tmp_path)
    first = evidence.envelope_for(mode="canary", cwd=project)["inputHash"]
    again = evidence.envelope_for(mode="canary", cwd=project)["inputHash"]
    full = evidence.envelope_for(mode="full", cwd=project)["inputHash"]
    assert first == again != full


def test_a_run_writes_nothing_outside_the_fixture(tmp_path):
    project = _copy_fixture("clean", tmp_path)
    before = sorted(p.relative_to(project) for p in project.rglob("*"))
    completed = subprocess.run(
        [sys.executable, "-m", "pygate.evidence", "--mode", "canary"],
        cwd=project, env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        text=True, capture_output=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "pass"
    assert sorted(p.relative_to(project) for p in project.rglob("*")) == before


def test_git_sha_marks_a_tree_whose_commit_does_not_describe_the_code(tmp_path):
    assert evidence.git_sha(tmp_path) is None

    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    run("init", "-q")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("one\n")
    run("add", "-A")
    run("commit", "-qm", "first")
    clean = evidence.git_sha(tmp_path)
    assert clean and len(clean) == 40
    (tmp_path / "a.txt").write_text("two\n")
    assert evidence.git_sha(tmp_path) == f"{clean}-dirty"
