from __future__ import annotations

from pathlib import Path

import pytest

from pygate.config import ConfigError, load_config


@pytest.mark.parametrize(
    ("filename", "content", "needle"),
    [
        # Typo in a gate key would silently skip the test gate in canary mode.
        ("pyproject.toml", "[tool.pygate.gates]\ntest_in_canry = true\n", "test_in_canry"),
        # Misspelled table name is otherwise ignored entirely.
        ("pyproject.toml", "[tool.pygate.gate]\ntest_in_canary = true\n", "gate"),
        # README pyproject snippet pasted into pygate.toml is otherwise ignored entirely.
        ("pygate.toml", "[tool.pygate.gates]\ntest_in_canary = true\n", "pygate.toml"),
        # String "false" is truthy: would silently enable shell parsing.
        ("pyproject.toml", '[tool.pygate]\nallow_unsafe_shell = "false"\n', "allow_unsafe_shell"),
        ("pyproject.toml", '[tool.pygate.gates]\ntest_in_canary = "false"\n', "test_in_canary"),
        ("pygate.toml", "[commands]\ntests = 'pytest -q'\n", "tests"),
        ("pygate.toml", "[commands]\ntest = 5\n", "commands.test"),
        ("pygate.toml", '[policy]\ncommand_timeout_seconds = "abc"\n', "command_timeout_seconds"),
        ("pygate.toml", "[policy]\nmax_attempt = 5\n", "max_attempt"),
    ],
)
def test_invalid_config_is_rejected_not_ignored(tmp_path: Path, filename: str, content: str, needle: str):
    (tmp_path / filename).write_text(content)
    with pytest.raises(ConfigError, match=needle):
        load_config(tmp_path)


def test_valid_readme_config_is_accepted(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pygate]\nallow_unsafe_shell = false\n"
        "[tool.pygate.policy]\nmax_attempts = 3\ncommand_timeout_seconds = 1.5\n"
        '[tool.pygate.commands]\nlint = "ruff check ."\ntest = ["pytest", "-q"]\n'
        "[tool.pygate.gates]\ntest_in_canary = true\n"
    )
    config = load_config(tmp_path)
    assert config["gates"]["test_in_canary"] is True
    assert config["allow_unsafe_shell"] is False
    assert config["commands"]["test"] == ["pytest", "-q"]
    assert config["policy"]["command_timeout_seconds"] == 1.5
