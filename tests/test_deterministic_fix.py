from __future__ import annotations

from unittest.mock import patch

from pygate.deterministic_fix import _collect_scoped_files, _is_eligible, run_deterministic_prefix
from pygate.models import (
    FailuresPayload,
    Finding,
    GateName,
    GateResult,
    GateStatus,
    RunMode,
    RunStatus,
    Severity,
)


class TestIsEligible:
    def test_accepts_py_file(self):
        assert _is_eligible("src/foo.py") is True

    def test_rejects_non_py_file(self):
        assert _is_eligible("src/foo.js") is False

    def test_rejects_excluded_dir_pygate(self):
        assert _is_eligible(".pygate/foo.py") is False

    def test_rejects_excluded_dir_git(self):
        assert _is_eligible(".git/hooks/pre-commit.py") is False

    def test_rejects_excluded_dir_venv(self):
        assert _is_eligible(".venv/lib/foo.py") is False

    def test_rejects_pycache(self):
        assert _is_eligible("src/__pycache__/foo.py") is False

    def test_rejects_absolute_path(self):
        assert _is_eligible("/usr/lib/foo.py") is False

    def test_rejects_path_traversal(self):
        assert _is_eligible("../secret.py") is False

    def test_accepts_nested_py_file(self):
        assert _is_eligible("src/gates/ruff.py") is True

    def test_accepts_filename_containing_double_dot(self):
        assert _is_eligible("src/version..py") is True


class TestCollectScopedFiles:
    def _make_failures(self, *, changed_files=None, finding_files=None):
        findings = []
        if finding_files:
            for i, files in enumerate(finding_files):
                findings.append(
                    Finding(
                        id=f"f{i}",
                        gate=GateName.LINT,
                        severity=Severity.HIGH,
                        summary="issue",
                        files=files,
                        actual=1,
                        threshold=0,
                    )
                )
        return FailuresPayload(
            run_id="test",
            mode=RunMode.CANARY,
            status=RunStatus.FAIL,
            timestamp="2026-01-01T00:00:00Z",
            changed_files=changed_files or [],
            gates=[GateResult(name=GateName.LINT, status=GateStatus.FAIL, duration_ms=10)],
            findings=findings,
        )

    def test_collects_from_changed_files(self):
        f = self._make_failures(changed_files=["src/a.py", "src/b.py"])
        result = _collect_scoped_files(f)
        assert "src/a.py" in result
        assert "src/b.py" in result

    def test_collects_from_findings(self):
        f = self._make_failures(finding_files=[["src/c.py"]])
        result = _collect_scoped_files(f)
        assert "src/c.py" in result

    def test_deduplicates(self):
        f = self._make_failures(changed_files=["src/a.py"], finding_files=[["src/a.py"]])
        result = _collect_scoped_files(f)
        assert result.count("src/a.py") == 1

    def test_filters_ineligible(self):
        f = self._make_failures(changed_files=["src/a.py", "readme.md", ".git/config.py"])
        result = _collect_scoped_files(f)
        assert "src/a.py" in result
        assert "readme.md" not in result


class TestRunDeterministicPrefix:
    def _make_failures_with_lint(self):
        return FailuresPayload(
            run_id="test",
            mode=RunMode.CANARY,
            status=RunStatus.FAIL,
            timestamp="2026-01-01T00:00:00Z",
            changed_files=["src/foo.py"],
            gates=[GateResult(name=GateName.LINT, status=GateStatus.FAIL, duration_ms=10)],
            findings=[
                Finding(
                    id="f0",
                    gate=GateName.LINT,
                    severity=Severity.HIGH,
                    summary="lint issue",
                    files=["src/foo.py"],
                    actual=1,
                    threshold=0,
                )
            ],
        )

    @patch("pygate.deterministic_fix.run_command")
    def test_returns_two_actions_on_lint_failure(self, mock_run, tmp_path):
        from pygate.models import CommandTrace

        mock_run.return_value = CommandTrace(
            command="ruff",
            cwd=str(tmp_path),
            started_at="2026-01-01T00:00:00Z",
            duration_ms=50,
            exit_code=0,
            stdout="",
            stderr="",
        )
        failures = self._make_failures_with_lint()
        actions = run_deterministic_prefix(cwd=tmp_path, failures=failures)
        assert len(actions) == 2
        assert actions[0]["rule_id"] == "RUFF_AUTOFIX"
        assert actions[1]["rule_id"] == "RUFF_FORMAT"

    def test_returns_empty_when_no_lint_failure(self, tmp_path):
        failures = FailuresPayload(
            run_id="test",
            mode=RunMode.CANARY,
            status=RunStatus.FAIL,
            timestamp="2026-01-01T00:00:00Z",
            changed_files=["src/foo.py"],
            gates=[GateResult(name=GateName.TYPECHECK, status=GateStatus.FAIL, duration_ms=10)],
            findings=[
                Finding(
                    id="f0",
                    gate=GateName.TYPECHECK,
                    severity=Severity.HIGH,
                    summary="type error",
                    files=["src/foo.py"],
                    actual=1,
                    threshold=0,
                )
            ],
        )
        actions = run_deterministic_prefix(cwd=tmp_path, failures=failures)
        assert actions == []

    @patch("pygate.deterministic_fix.run_command")
    def test_ruff_fix_exit_code_1_is_accepted(self, mock_run, tmp_path):
        from pygate.models import CommandTrace

        mock_run.return_value = CommandTrace(
            command="ruff",
            cwd=str(tmp_path),
            started_at="2026-01-01T00:00:00Z",
            duration_ms=50,
            exit_code=1,
            stdout="",
            stderr="",
        )
        failures = self._make_failures_with_lint()
        actions = run_deterministic_prefix(cwd=tmp_path, failures=failures)
        assert actions[0]["accepted"] is True
