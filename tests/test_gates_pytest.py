from __future__ import annotations

import json
from pathlib import Path

from pygate.gates.pytest_gate import parse_pytest_output
from pygate.models import GateName, Severity


class TestParsePytestOutput:
    def test_parse_fixture(self, sample_pytest_report: dict, tmp_path: Path):
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(sample_pytest_report))

        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp/project"))

        assert len(findings) == 2

        f0 = findings[0]
        assert f0.gate == GateName.TEST
        assert f0.severity == Severity.HIGH
        assert "test_divide_by_zero" in f0.summary
        assert f0.files == ["tests/test_math.py"]
        assert f0.raw["outcome"] == "failed"

        f1 = findings[1]
        assert "test_get_user" in f1.summary
        assert f1.files == ["tests/test_api.py"]

    def test_no_report_file(self):
        findings = parse_pytest_output("", "", 1, Path("/nonexistent/report.json"), Path("/tmp"))
        assert findings == []

    def test_empty_report(self, tmp_path: Path):
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps({"tests": [], "summary": {"passed": 0, "failed": 0}}))
        findings = parse_pytest_output("", "", 0, report_path, Path("/tmp"))
        assert findings == []

    def test_longrepr_truncation(self, tmp_path: Path):
        report = {
            "tests": [
                {
                    "nodeid": "tests/test_long.py::test_verbose",
                    "outcome": "failed",
                    "call": {
                        "duration": 0.1,
                        "longrepr": "x" * 1000,
                    },
                }
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))
        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))
        assert len(findings) == 1
        assert len(findings[0].raw["longrepr"]) == 503  # 500 + "..."

    def test_invalid_json_report(self, tmp_path: Path):
        report_path = tmp_path / "report.json"
        report_path.write_text("not json")
        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))
        assert findings == []

    def test_setup_error_preserves_longrepr(self, tmp_path: Path):
        """A fixture that raises reports outcome=error with detail in setup and no call phase."""
        longrepr = (
            "@pytest.fixture\n"
            "    def db_conn():\n"
            ">       raise RuntimeError('cannot reach database')\n"
            "E       RuntimeError: cannot reach database\n\n"
            "tests/conftest.py:12: RuntimeError"
        )
        report = {
            "tests": [
                {
                    "nodeid": "tests/test_db.py::test_query",
                    "outcome": "error",
                    "setup": {"duration": 0.02, "outcome": "failed", "longrepr": longrepr},
                    "teardown": {"duration": 0.001, "outcome": "passed"},
                }
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))

        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))

        assert len(findings) == 1
        finding = findings[0]
        assert finding.raw["longrepr"] == longrepr
        assert "RuntimeError: cannot reach database" in finding.raw["longrepr"]
        assert finding.raw["duration"] == 0.02
        assert finding.summary.startswith("tests/test_db.py::test_query: @pytest.fixture")

    def test_teardown_error_preserves_longrepr(self, tmp_path: Path):
        """A fixture that raises on teardown reports outcome=error with a clean call phase."""
        longrepr = (
            "    def db_conn():\n"
            "        yield conn\n"
            ">       conn.close()\n"
            "E       OSError: connection already closed\n\n"
            "tests/conftest.py:19: OSError"
        )
        report = {
            "tests": [
                {
                    "nodeid": "tests/test_db.py::test_insert",
                    "outcome": "error",
                    "setup": {"duration": 0.001, "outcome": "passed"},
                    "call": {"duration": 0.05, "outcome": "passed"},
                    "teardown": {"duration": 0.03, "outcome": "failed", "longrepr": longrepr},
                }
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))

        findings = parse_pytest_output("", "", 1, report_path, Path("/tmp"))

        assert len(findings) == 1
        finding = findings[0]
        assert finding.raw["longrepr"] == longrepr
        assert "OSError: connection already closed" in finding.raw["longrepr"]
        assert finding.raw["duration"] == 0.03
        assert finding.summary.startswith("tests/test_db.py::test_insert:     def db_conn():")
