from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from pygate.api import evaluate
from pygate.contract import GateResultV1, serialize_gate_result
from pygate.exec import OUTPUT_TRUNCATION_MARKER, run_command
from pygate.models import RunMode
from pygate.run_command import execute_run
from pygate.snapshot import snapshot_digest


def _passing_config() -> dict:
    return {
        "config_version": "pygate-config/v1",
        "source": "fixture",
        "allow_unsafe_shell": False,
        "policy": {
            "command_timeout_seconds": 2,
            "gate_timeout_seconds": 2,
            "output_cap_bytes": 4096,
        },
        "commands": {
            "lint": [sys.executable, "-c", "print('[]')"],
            "typecheck": [sys.executable, "-c", "print('{\"generalDiagnostics\": []}')"],
        },
        "gates": {},
    }


def test_metacharacters_are_data_by_default(tmp_path: Path):
    marker = tmp_path / "should-not-exist"
    payload = f"$(touch {marker})"
    trace = run_command(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
        cwd=tmp_path,
    )
    assert trace.exit_code == 0
    assert payload in trace.stdout
    assert not marker.exists()
    assert trace.shell is False


def test_spaces_in_executable_and_argument_paths(tmp_path: Path):
    script = tmp_path / "folder with spaces" / "tool with spaces.py"
    script.parent.mkdir()
    script.write_text("import sys; print(sys.argv[1])\n", encoding="utf-8")
    argument = tmp_path / "input with spaces.txt"
    trace = run_command([sys.executable, str(script), str(argument)], cwd=tmp_path)
    assert trace.exit_code == 0
    assert str(argument) in trace.stdout


def test_timeout_terminates_descendants(tmp_path: Path):
    marker = tmp_path / "descendant-wrote-after-timeout"
    child_code = f"import time; time.sleep(2); Path({str(marker)!r}).write_text('bad')"
    parent_code = (
        f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); time.sleep(10)"
    )
    trace = run_command([sys.executable, "-c", parent_code], cwd=tmp_path, timeout_seconds=0.2)
    assert trace.timed_out is True
    assert trace.exit_code == 1
    time.sleep(0.4)
    assert not marker.exists()


def test_oversized_output_is_capped_with_marker(tmp_path: Path):
    trace = run_command(
        [sys.executable, "-c", "print('x' * 1000)"],
        cwd=tmp_path,
        output_cap_bytes=64,
    )
    assert trace.output_truncated is True
    assert OUTPUT_TRUNCATION_MARKER in trace.stdout


def test_missing_executable_is_structured(tmp_path: Path):
    trace = run_command(["pygate-tool-that-does-not-exist"], cwd=tmp_path)
    assert trace.exit_code == 127
    assert trace.missing_executable is True
    assert "executable not found" in trace.diagnostics


def test_malformed_command_is_structured(tmp_path: Path):
    trace = run_command("echo 'unterminated", cwd=tmp_path)
    assert trace.exit_code == 2
    assert trace.error
    assert "invalid command arguments" in trace.diagnostics


def test_signal_is_recorded(tmp_path: Path):
    trace = run_command(
        [sys.executable, "-c", f"import os, signal; os.kill(os.getpid(), signal.{signal.SIGTERM.name})"],
        cwd=tmp_path,
    )
    assert trace.signal == signal.SIGTERM
    assert trace.exit_code == -signal.SIGTERM


def test_evaluate_is_side_effect_free_and_binds_contract(tmp_path: Path):
    checked = tmp_path / "input.py"
    checked.write_text("print('ok')\n", encoding="utf-8")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    result = evaluate(
        mode=RunMode.CANARY,
        checked_paths=["input.py"],
        cwd=tmp_path,
        config=_passing_config(),
    )
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
    assert result.schema == "gate-result/v1"
    assert result.status == "pass"
    assert result.snapshot_digest
    assert result.checked_paths == ["input.py"]
    assert result.config_identity == "fixture"
    assert result.config_digest
    assert result.package_version
    assert result.command_versions
    assert result.elapsed_ms >= 0


def test_changed_input_is_marked_stale(tmp_path: Path):
    checked = tmp_path / "input.py"
    checked.write_text("before\n", encoding="utf-8")
    config = _passing_config()
    config["commands"]["lint"] = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('input.py').write_text('after'); print('[]')",
    ]
    result = evaluate(mode=RunMode.CANARY, checked_paths=["input.py"], cwd=tmp_path, config=config)
    assert result.snapshot_changed is True
    assert result.status == "fail"
    assert "checked input changed" in result.errors[0]


def test_snapshot_preserves_symlink_identity(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("first\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to("target.txt")

    first_digest, first_paths = snapshot_digest(["link.txt"], cwd=tmp_path)
    target.write_text("second\n", encoding="utf-8")
    second_digest, second_paths = snapshot_digest(["link.txt"], cwd=tmp_path)

    assert first_paths == second_paths == ["link.txt"]
    assert first_digest == second_digest


def test_external_artifact_directory_does_not_pollute_cwd(tmp_path: Path):
    output_dir = tmp_path.parent / f"pygate-output-{os.getpid()}"
    try:
        result = execute_run(
            mode=RunMode.CANARY,
            changed_files=[],
            cwd=tmp_path,
            output_dir=output_dir,
        )
        assert Path(result["gate_result_path"]).parent == output_dir
        assert (output_dir / "gate-result.json").exists()
        assert not (tmp_path / ".pygate").exists()
    finally:
        for path in output_dir.glob("*") if output_dir.exists() else []:
            path.unlink()
        if output_dir.exists():
            output_dir.rmdir()


def test_contract_serialization_is_deterministic():
    base = {
        "schema": "gate-result/v1",
        "status": "pass",
        "snapshot_digest": "abc",
        "checks": [],
        "findings": [],
        "elapsed_ms": 1,
        "command_versions": {"b": "2", "a": "1"},
    }
    one = GateResultV1(**base)
    two = GateResultV1(**{**base, "command_versions": {"a": "1", "b": "2"}})
    assert serialize_gate_result(one) == serialize_gate_result(two)


def test_schema_fixture_has_required_contract_fields():
    schema = json.loads(Path("schemas/gate-result-v1.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema"]["const"] == "gate-result/v1"
    assert set(
        [
            "status",
            "snapshot_digest",
            "checked_paths",
            "checks",
            "findings",
            "command_versions",
            "elapsed_ms",
            "output_truncated",
            "errors",
        ]
    ).issubset(schema["required"])


def test_shared_gate_result_fixtures_match_canonical_schema():
    schema = json.loads(Path("schemas/gate-result-v1.schema.json").read_text(encoding="utf-8"))
    fixtures = json.loads(Path("tests/fixtures/gate-result-v1.fixtures.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for case in fixtures["cases"]:
        errors = list(validator.iter_errors(case["value"]))
        assert (not errors) is case["valid"], (case["name"], errors)
