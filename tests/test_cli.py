from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pygate.cli import main
from pygate.contract import GateResultV1


class TestCLIParsing:
    def test_no_command_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 0

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "pygate" in captured.out

    def test_run_requires_mode(self):
        with pytest.raises(SystemExit) as exc:
            main(["run", "--changed-files", "foo.txt"])
        assert exc.value.code != 0

    @patch("pygate.cli.evaluate")
    def test_run_without_changed_files_uses_whole_project_commands(self, mock_evaluate):
        mock_evaluate.return_value = GateResultV1(status="pass", snapshot_digest="test")
        with pytest.raises(SystemExit) as exc:
            main(["run", "--mode", "canary"])
        assert exc.value.code == 0
        assert mock_evaluate.call_args.kwargs["checked_paths"] == []

    def test_summarize_requires_input(self):
        with pytest.raises(SystemExit) as exc:
            main(["summarize"])
        assert exc.value.code != 0

    def test_repair_requires_input(self):
        with pytest.raises(SystemExit) as exc:
            main(["repair"])
        assert exc.value.code != 0


class TestCLIRun:
    @patch("pygate.cli.evaluate")
    @patch("pygate.cli.load_changed_files")
    def test_run_pass_exits_0(self, mock_load, mock_evaluate, capsys, tmp_path: Path):
        mock_load.return_value = ["src/foo.py"]
        mock_evaluate.return_value = GateResultV1(status="pass", snapshot_digest="test")

        changed = tmp_path / "changed.txt"
        changed.write_text("src/foo.py\n")

        with pytest.raises(SystemExit) as exc:
            main(["run", "--mode", "canary", "--changed-files", str(changed)])
        assert exc.value.code == 0

    @patch("pygate.cli.evaluate")
    @patch("pygate.cli.load_changed_files")
    def test_run_fail_exits_1(self, mock_load, mock_evaluate, capsys, tmp_path: Path):
        mock_load.return_value = ["src/foo.py"]
        mock_evaluate.return_value = GateResultV1(status="fail", snapshot_digest="test")

        changed = tmp_path / "changed.txt"
        changed.write_text("src/foo.py\n")

        with pytest.raises(SystemExit) as exc:
            main(["run", "--mode", "canary", "--changed-files", str(changed)])
        assert exc.value.code == 1


class TestCLIRepair:
    @patch("pygate.cli.execute_repair")
    def test_repair_pass_exits_0(self, mock_repair, tmp_path: Path):
        mock_repair.return_value = {"status": "pass", "attempts": []}

        with pytest.raises(SystemExit) as exc:
            main(["repair", "--input", str(tmp_path / "failures.json")])
        assert exc.value.code == 0

    @patch("pygate.cli.execute_repair")
    def test_repair_escalated_exits_2(self, mock_repair, tmp_path: Path):
        mock_repair.return_value = {"status": "escalated", "reason_code": "NO_IMPROVEMENT"}

        with pytest.raises(SystemExit) as exc:
            main(["repair", "--input", str(tmp_path / "failures.json")])
        assert exc.value.code == 2
