from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pygate.gates import run_deterministic_gates
from pygate.models import CommandTrace, GateName, RunMode


def _make_trace(exit_code: int = 0, stdout: str = "", stderr: str = "") -> CommandTrace:
    return CommandTrace(
        command="test",
        cwd="/tmp",
        started_at="2026-01-01T00:00:00Z",
        duration_ms=100,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )


class TestRunDeterministicGates:
    @patch("pygate.gates.run_command")
    def test_full_mode_runs_all_three_gates(self, mock_run, tmp_path: Path):
        (tmp_path / ".pygate").mkdir()
        mock_run.side_effect = [
            _make_trace(0, "[]"),  # ruff
            _make_trace(0, json.dumps({"generalDiagnostics": [], "summary": {"errorCount": 0}})),  # pyright
            _make_trace(0, ""),  # pytest (no report file, returns empty findings)
        ]
        config = {"gates": {}, "commands": {}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.FULL, cwd=tmp_path, config=config, changed_files=[]
        )
        gate_names = [r.name for r in results]
        assert GateName.LINT in gate_names
        assert GateName.TYPECHECK in gate_names
        assert GateName.TEST in gate_names
        assert all(r.status.value in ("pass", "fail") for r in results if r.name != GateName.TEST)

    @patch("pygate.gates.run_command")
    def test_typecheck_failure_produces_findings(self, mock_run, tmp_path: Path):
        pyright_output = {
            "generalDiagnostics": [
                {
                    "file": str(tmp_path / "src/foo.py"),
                    "severity": "error",
                    "message": "Type error",
                    "rule": "reportGeneralClassIssues",
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 10}},
                }
            ],
            "summary": {"errorCount": 1},
        }
        mock_run.side_effect = [
            _make_trace(0, "[]"),  # ruff passes
            _make_trace(1, json.dumps(pyright_output)),  # pyright fails
        ]
        config = {"gates": {}, "commands": {}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.CANARY, cwd=tmp_path, config=config, changed_files=[]
        )
        assert any(f.gate == GateName.TYPECHECK for f in findings)
        assert len(findings) == 1

    @patch("pygate.gates.run_command")
    def test_test_in_canary_config_enables_test_gate(self, mock_run, tmp_path: Path):
        (tmp_path / ".pygate").mkdir()
        mock_run.side_effect = [
            _make_trace(0, "[]"),
            _make_trace(0, json.dumps({"generalDiagnostics": [], "summary": {"errorCount": 0}})),
            _make_trace(0, ""),  # pytest
        ]
        config = {"gates": {"test_in_canary": True}, "commands": {}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.CANARY, cwd=tmp_path, config=config, changed_files=[]
        )
        test_gate = next(r for r in results if r.name == GateName.TEST)
        assert test_gate.status.value != "skipped"

    @patch("pygate.gates.run_command")
    def test_fallback_finding_on_unparseable_output(self, mock_run, tmp_path: Path):
        mock_run.side_effect = [
            _make_trace(1, "not json"),  # ruff fails with unparseable output
            _make_trace(0, json.dumps({"generalDiagnostics": [], "summary": {"errorCount": 0}})),
        ]
        config = {"gates": {}, "commands": {}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.CANARY, cwd=tmp_path, config=config, changed_files=[]
        )
        assert len(findings) == 1
        assert "exit" in findings[0].id

    @patch("pygate.gates.run_command")
    def test_custom_command_from_config(self, mock_run, tmp_path: Path):
        mock_run.side_effect = [
            _make_trace(0, "[]"),  # custom lint command
            _make_trace(0, json.dumps({"generalDiagnostics": [], "summary": {"errorCount": 0}})),
        ]
        config = {"gates": {}, "commands": {"lint": "custom-ruff check ."}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.CANARY, cwd=tmp_path, config=config, changed_files=[]
        )
        assert mock_run.call_args_list[0][0][0] == "custom-ruff check ."


class TestTestGateStaleReport:
    @patch("pygate.gates.run_command")
    def test_stale_pytest_report_is_ignored_without_artifact_dir(self, mock_run, tmp_path: Path):
        """Without artifact_dir no fresh JSON report is requested, so a leftover one must not be read."""
        pygate_dir = tmp_path / ".pygate"
        pygate_dir.mkdir()
        (pygate_dir / "pytest-report.json").write_text(
            json.dumps(
                {
                    "tests": [
                        {
                            "nodeid": "tests/test_stale.py::test_removed",
                            "outcome": "failed",
                            "call": {"longrepr": "AssertionError: from a previous run", "duration": 0.1},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        mock_run.side_effect = [
            _make_trace(0, "[]"),  # ruff passes
            _make_trace(0, json.dumps({"generalDiagnostics": [], "summary": {"errorCount": 0}})),  # pyright passes
            _make_trace(1, "1 failed in 0.01s"),  # pytest fails, writes no report
        ]
        config = {"gates": {}, "commands": {}}
        results, findings, traces = run_deterministic_gates(
            mode=RunMode.FULL, cwd=tmp_path, config=config, changed_files=[], artifact_dir=None
        )

        assert "--json-report" not in mock_run.call_args_list[2][0][0]
        test_findings = [f for f in findings if f.gate == GateName.TEST]
        assert [f.id for f in test_findings] == ["test_exit_1"]
        assert not any("test_stale" in f.id for f in test_findings)
