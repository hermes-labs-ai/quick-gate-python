from __future__ import annotations

from pygate.exec import run_command


class TestRunCommand:
    def test_captures_stdout(self, tmp_path):
        trace = run_command("echo hello", cwd=tmp_path)
        assert trace.stdout.strip() == "hello"
        assert trace.exit_code == 0

    def test_captures_stderr(self, tmp_path):
        trace = run_command("echo err >&2", cwd=tmp_path, shell=True)
        assert "err" in trace.stderr
        assert trace.exit_code == 0

    def test_returns_exit_code(self, tmp_path):
        trace = run_command("exit 42", cwd=tmp_path, shell=True)
        assert trace.exit_code == 42

    def test_timeout_sets_timed_out_flag(self, tmp_path):
        trace = run_command("sleep 10", cwd=tmp_path, timeout_seconds=1)
        assert trace.timed_out is True
        assert trace.exit_code == 1

    def test_records_duration_ms(self, tmp_path):
        trace = run_command("echo fast", cwd=tmp_path)
        assert trace.duration_ms >= 0

    def test_records_started_at(self, tmp_path):
        trace = run_command("echo test", cwd=tmp_path)
        assert "T" in trace.started_at

    def test_custom_cwd(self, tmp_path):
        trace = run_command("pwd", cwd=tmp_path)
        assert str(tmp_path) in trace.stdout

    def test_custom_env(self, tmp_path):
        trace = run_command("echo $MY_TEST_VAR", cwd=tmp_path, env={"MY_TEST_VAR": "hello123"}, shell=True)
        assert "hello123" in trace.stdout

    def test_records_command(self, tmp_path):
        trace = run_command("echo test", cwd=tmp_path)
        assert trace.command == "echo test"
