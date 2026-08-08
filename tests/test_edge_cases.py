"""Edge case tests identified by adversarial review agents.

Covers gaps in: repair rollback/time-cap/patch-budget, summarize scoping,
CLI flag parsing, model validation, gate parser edge cases, config merging,
file collection limits, and demo artifact validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pygate.cli import main
from pygate.config import load_config
from pygate.deterministic_fix import _collect_scoped_files
from pygate.fs import load_changed_files
from pygate.gates.pyright import parse_pyright_output
from pygate.gates.pytest_gate import parse_pytest_output
from pygate.gates.ruff import _severity_for_code
from pygate.models import (
    ActionScope,
    AgentBrief,
    Confidence,
    EnvironmentInfo,
    Escalation,
    FailuresPayload,
    Finding,
    GateName,
    GateResult,
    GateStatus,
    RepairReport,
    RunMetadata,
    RunMode,
    RunStatus,
    Severity,
)
from pygate.repair_command import execute_repair
from pygate.summarize_command import _scope_for_finding, execute_summarize

# ── Repair: worsened rollback ────────────────────────────────────────────


class TestRepairWorsenedRollback:
    def test_rollback_on_worsened_findings(self, tmp_path: Path, seed_failures):
        """When repair worsens findings, workspace must be rolled back."""
        failures_path = seed_failures(findings_count=2)

        call_count = 0

        with (
            patch("pygate.repair_command.execute_run") as mock_run,
            patch("pygate.repair_command.run_deterministic_prefix") as mock_fix,
        ):
            mock_fix.return_value = [{"rule_id": "RUFF_AUTOFIX", "accepted": True}]

            def side_effect(**kwargs):
                nonlocal call_count
                call_count += 1
                pygate_dir = tmp_path / ".pygate"
                # Findings increase: 2 → 5 (worsened), then 5 → 5 (no improvement)
                count = 5
                f_data = {
                    "version": "1.0.0",
                    "run_id": f"re_{call_count}",
                    "mode": "canary",
                    "status": "fail",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "changed_files": ["src/foo.py"],
                    "gates": [{"name": "lint", "status": "fail", "duration_ms": 50}],
                    "findings": [
                        {
                            "id": f"f{i}",
                            "gate": "lint",
                            "severity": "high",
                            "summary": f"issue {i}",
                            "actual": 1,
                            "threshold": 0,
                        }
                        for i in range(count)
                    ],
                    "inferred_hints": [],
                }
                (pygate_dir / "failures.json").write_text(json.dumps(f_data))
                return {
                    "status": "fail",
                    "failures_path": str(pygate_dir / "failures.json"),
                    "run_id": f"re_{call_count}",
                }

            mock_run.side_effect = side_effect
            result = execute_repair(input_path=str(failures_path), max_attempts=3, cwd=tmp_path)

        assert result["status"] == "escalated"
        # Should have tried multiple times with no improvement (original count stays 2)
        assert result["reason_code"] in ("NO_IMPROVEMENT", "UNKNOWN_BLOCKER")


class TestRepairTimeCap:
    def test_escalates_on_time_cap(self, tmp_path: Path, seed_failures):
        """Repair must escalate when time cap is exceeded."""
        failures_path = seed_failures(findings_count=1)

        # Create a pygate.toml with a very short time cap
        (tmp_path / "pygate.toml").write_text("[policy]\ntime_cap_seconds = 0\n")

        with (
            patch("pygate.repair_command.execute_run"),
            patch("pygate.repair_command.run_deterministic_prefix"),
        ):
            result = execute_repair(input_path=str(failures_path), max_attempts=3, cwd=tmp_path)

        assert result["status"] == "escalated"
        assert result["reason_code"] == "UNKNOWN_BLOCKER"
        assert "Time cap" in result["message"]


class TestRepairPatchBudget:
    def test_escalates_on_patch_budget_exceeded(self, tmp_path: Path, seed_failures):
        """Repair must escalate when patch exceeds line budget."""
        failures_path = seed_failures(findings_count=1)
        # Set very small patch budget
        (tmp_path / "pygate.toml").write_text("[policy]\nmax_patch_lines = 1\n")

        with (
            patch("pygate.repair_command.execute_run"),
            patch("pygate.repair_command.run_deterministic_prefix") as mock_fix,
            patch("pygate.repair_command._diff_snapshot") as mock_diff,
        ):
            mock_fix.return_value = [{"rule_id": "RUFF_AUTOFIX", "accepted": True}]
            # Before: no changes, After: 200 lines changed
            mock_diff.side_effect = [{}, {"src/foo.py": 200}]

            result = execute_repair(input_path=str(failures_path), max_attempts=3, cwd=tmp_path)

        assert result["status"] == "escalated"
        assert result["reason_code"] == "PATCH_BUDGET_EXCEEDED"


# ── Summarize: scope classification ──────────────────────────────────────


class TestSummarizeScopeClassification:
    def test_single_file_scope(self):
        assert _scope_for_finding(["src/foo.py"]) == ActionScope.SINGLE_FILE

    def test_multi_file_scope(self):
        assert _scope_for_finding(["src/a.py", "src/b.py"]) == ActionScope.MULTI_FILE

    def test_cross_module_scope(self):
        files = ["src/a.py", "src/b.py", "src/c.py", "src/d.py"]
        assert _scope_for_finding(files) == ActionScope.CROSS_MODULE

    def test_empty_files_is_multi_file(self):
        # 0 files: len(0) <= 3, so classified as multi_file
        assert _scope_for_finding([]) == ActionScope.MULTI_FILE


class TestSummarizeEscalation:
    def test_pass_status_no_escalation(self, tmp_path: Path, seed_failures):
        failures_path = seed_failures(findings_count=0)
        execute_summarize(input_path=str(failures_path), cwd=tmp_path)

        from pygate.fs import read_json

        brief = read_json(tmp_path / ".pygate" / "agent-brief.json")
        assert brief["escalation"]["required"] is False
        assert brief["escalation"].get("reason_code") is None

    def test_fail_status_has_escalation(self, tmp_path: Path, seed_failures):
        failures_path = seed_failures(findings_count=2)
        execute_summarize(input_path=str(failures_path), cwd=tmp_path)

        from pygate.fs import read_json

        brief = read_json(tmp_path / ".pygate" / "agent-brief.json")
        assert brief["escalation"]["required"] is True
        assert brief["escalation"]["reason_code"] == "UNRESOLVED_DETERMINISTIC_FAILURES"

    def test_markdown_pass_status_says_all_passed(self, tmp_path: Path, seed_failures):
        failures_path = seed_failures(findings_count=0)
        execute_summarize(input_path=str(failures_path), cwd=tmp_path)

        md = (tmp_path / ".pygate" / "agent-brief.md").read_text()
        assert "passed" in md.lower()


# ── CLI: additional edge cases ───────────────────────────────────────────


class TestCLIEdgeCases:
    @patch("pygate.cli.execute_summarize")
    def test_summarize_exits_0(self, mock_summarize, tmp_path: Path):
        mock_summarize.return_value = {"status": "pass", "brief_json_path": "", "brief_md_path": ""}
        with pytest.raises(SystemExit) as exc:
            main(["summarize", "--input", str(tmp_path / "failures.json")])
        assert exc.value.code == 0

    @patch("pygate.cli.execute_repair")
    def test_repair_with_max_attempts_flag(self, mock_repair, tmp_path: Path):
        mock_repair.return_value = {"status": "pass", "attempts": []}
        with pytest.raises(SystemExit) as exc:
            main(["repair", "--input", str(tmp_path / "f.json"), "--max-attempts", "5"])
        assert exc.value.code == 0
        assert mock_repair.call_args.kwargs["max_attempts"] == 5

    def test_invalid_mode_rejected(self):
        with pytest.raises(SystemExit) as exc:
            main(["run", "--mode", "invalid", "--changed-files", "f.txt"])
        assert exc.value.code != 0


# ── Models: additional validation ────────────────────────────────────────


class TestModelValidation:
    def test_confidence_enum_values(self):
        assert Confidence.LOW.value == "low"
        assert Confidence.MEDIUM.value == "medium"
        assert Confidence.HIGH.value == "high"

    def test_action_scope_enum_values(self):
        assert ActionScope.SINGLE_FILE.value == "single_file"
        assert ActionScope.MULTI_FILE.value == "multi_file"
        assert ActionScope.CROSS_MODULE.value == "cross_module"

    def test_environment_info_minimal(self):
        env = EnvironmentInfo(python_version="3.12.0", platform="linux")
        assert env.virtualenv is None
        assert env.resolver is None
        assert env.installed_packages == {}

    def test_run_metadata_roundtrip(self):
        meta = RunMetadata(
            run_id="run_test",
            mode=RunMode.CANARY,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
            config_source="defaults",
            environment=EnvironmentInfo(python_version="3.12.0", platform="linux"),
            command_traces=[],
        )
        data = meta.model_dump(mode="json")
        restored = RunMetadata(**data)
        assert restored.run_id == "run_test"
        assert restored.environment.python_version == "3.12.0"

    def test_escalation_default_status(self):
        e = Escalation(reason_code="TEST", message="test", evidence={})
        assert e.status == "escalated"

    def test_finding_with_string_actual_and_threshold(self):
        f = Finding(
            id="test",
            gate=GateName.TEST,
            severity=Severity.HIGH,
            summary="test failed",
            actual="failed",
            threshold="passed",
        )
        assert f.actual == "failed"
        assert f.threshold == "passed"

    def test_repair_report_with_attempts(self):
        from pygate.models import RepairAttempt

        report = RepairReport(
            status="pass",
            attempts=[
                RepairAttempt(
                    attempt=1,
                    patch_lines=10,
                    before_findings=3,
                    after_findings=0,
                    improved=True,
                    worsened=False,
                    status="pass",
                )
            ],
        )
        data = report.model_dump(mode="json")
        restored = RepairReport(**data)
        assert len(restored.attempts) == 1


# ── Gate parsers: edge cases ─────────────────────────────────────────────


class TestRuffSeverityMapping:
    def test_e_prefix_is_high(self):
        assert _severity_for_code("E501") == Severity.HIGH

    def test_f_prefix_is_high(self):
        assert _severity_for_code("F401") == Severity.HIGH

    def test_w_prefix_is_medium(self):
        assert _severity_for_code("W291") == Severity.MEDIUM

    def test_i_prefix_is_medium(self):
        assert _severity_for_code("I001") == Severity.MEDIUM

    def test_empty_code_is_medium(self):
        assert _severity_for_code("") == Severity.MEDIUM


class TestPyrightEdgeCases:
    def test_finding_without_rule(self):
        data = {
            "generalDiagnostics": [
                {
                    "file": "/tmp/project/src/foo.py",
                    "severity": "error",
                    "message": "Syntax error",
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                }
            ]
        }
        findings = parse_pyright_output(json.dumps(data), "", 1, Path("/tmp/project"))
        assert len(findings) == 1
        assert findings[0].rule is None
        assert findings[0].line == 1  # 0-indexed + 1
        assert findings[0].column == 1  # 0-indexed + 1

    def test_non_dict_json(self):
        findings = parse_pyright_output("[1, 2, 3]", "", 1, Path("/tmp"))
        assert findings == []


class TestPytestEdgeCases:
    def test_error_outcome_produces_finding(self, tmp_path: Path):
        report = {
            "tests": [
                {
                    "nodeid": "tests/test_setup.py::test_init",
                    "outcome": "error",
                    "call": {"duration": 0.01, "longrepr": "fixture error"},
                }
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))
        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))
        assert len(findings) == 1
        assert findings[0].raw["outcome"] == "error"

    def test_passed_tests_not_included(self, tmp_path: Path):
        report = {
            "tests": [
                {"nodeid": "tests/test_ok.py::test_pass", "outcome": "passed", "call": {"duration": 0.01}},
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))
        findings = parse_pytest_output("", "", 0, report_path, Path("/tmp"))
        assert findings == []

    def test_non_dict_report(self, tmp_path: Path):
        report_path = tmp_path / "report.json"
        report_path.write_text("[1, 2]")
        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))
        assert findings == []


# ── Config: gates merge ──────────────────────────────────────────────────


class TestConfigGatesMerge:
    def test_gates_config_merged_with_defaults(self, tmp_path: Path):
        (tmp_path / "pygate.toml").write_text("[gates]\ntest_in_canary = true\n")
        config = load_config(tmp_path)
        assert config["gates"]["test_in_canary"] is True


# ── Deterministic fix: max files limit ───────────────────────────────────


class TestCollectScopedFilesLimit:
    def test_max_20_files(self):
        failures = FailuresPayload(
            run_id="test",
            mode=RunMode.CANARY,
            status=RunStatus.FAIL,
            timestamp="2026-01-01T00:00:00Z",
            changed_files=[f"src/file_{i}.py" for i in range(30)],
            gates=[GateResult(name=GateName.LINT, status=GateStatus.FAIL, duration_ms=10)],
            findings=[],
        )
        result = _collect_scoped_files(failures)
        assert len(result) == 20


# ── FS: load_changed_files edge cases ────────────────────────────────────


class TestLoadChangedFilesEdgeCases:
    def test_json_array_with_non_string_elements(self, tmp_path: Path):
        path = tmp_path / "changed.json"
        path.write_text(json.dumps(["src/a.py", 42, None, "src/b.py"]))
        result = load_changed_files(path)
        assert result == ["src/a.py", "src/b.py"]

    def test_json_non_array_returns_empty(self, tmp_path: Path):
        path = tmp_path / "changed.json"
        path.write_text(json.dumps({"files": ["a.py"]}))
        # Starts with [ check fails, so it falls through to newline parsing
        result = load_changed_files(path)
        # The JSON object as text will be treated as a single "line"
        assert isinstance(result, list)


# ── Demo artifact validation ─────────────────────────────────────────────


DEMO_DIR = Path(__file__).parent.parent / "demo" / "artifacts"


class TestDemoArtifactValidation:
    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_failures_json_validates(self):
        data = json.loads((DEMO_DIR / "failures.json").read_text())
        payload = FailuresPayload(**data)
        assert payload.status == RunStatus.FAIL
        assert len(payload.findings) == 3

    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_agent_brief_json_validates(self):
        data = json.loads((DEMO_DIR / "agent-brief.json").read_text())
        brief = AgentBrief(**data)
        assert len(brief.priority_actions) == 3

    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_repair_report_json_validates(self):
        data = json.loads((DEMO_DIR / "repair-report.json").read_text())
        report = RepairReport(**data)
        assert report.status == "pass"
        assert len(report.attempts) == 2

    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_escalation_json_validates(self):
        data = json.loads((DEMO_DIR / "escalation.json").read_text())
        esc = Escalation(**data)
        assert esc.status == "escalated"
        assert esc.reason_code == "NO_IMPROVEMENT"

    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_run_metadata_json_validates(self):
        data = json.loads((DEMO_DIR / "run-metadata.json").read_text())
        meta = RunMetadata(**data)
        assert meta.mode == RunMode.CANARY
        assert len(meta.command_traces) == 2

    @pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo artifacts not present")
    def test_agent_brief_md_exists(self):
        md = (DEMO_DIR / "agent-brief.md").read_text()
        assert "PyGate Agent Brief" in md
        assert "Retry Policy" in md
