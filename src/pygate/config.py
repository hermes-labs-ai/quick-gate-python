from __future__ import annotations

import sys
from pathlib import Path

from pygate.constants import CONFIG_VERSION, DEFAULT_POLICY

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # pyright: ignore[reportMissingImports]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


_GATE_NAMES = frozenset({"lint", "typecheck", "test"})
_TOP_LEVEL_KEYS = frozenset({"config_version", "policy", "commands", "gates", "allow_unsafe_shell"})
_GATES_KEYS = frozenset({"test_in_canary"})


class ConfigError(ValueError):
    """Raised when a pygate configuration file has unknown keys or wrong value types."""


def load_config(cwd: Path | None = None) -> dict:
    cwd = cwd or Path.cwd()

    # Try pygate.toml first
    pygate_toml = cwd / "pygate.toml"
    if pygate_toml.exists():
        return _merge_config(_load_toml(pygate_toml), source=str(pygate_toml))

    # Try pyproject.toml [tool.pygate]
    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        full = _load_toml(pyproject)
        user_config = full.get("tool", {}).get("pygate", {})
        if user_config:
            return _merge_config(user_config, source=str(pyproject))

    return _defaults()


def _load_toml(path: Path) -> dict:
    if tomllib is None:
        raise ImportError(
            f"Cannot parse {path}: tomli package required on Python < 3.11. Install it with: pip install tomli"
        )
    with open(path, "rb") as f:
        return tomllib.load(f)


def _defaults() -> dict:
    return {
        "config_version": CONFIG_VERSION,
        "policy": dict(DEFAULT_POLICY),
        "commands": {},
        "gates": {},
        "allow_unsafe_shell": False,
        "source": "defaults",
    }


def _validate(user: dict, *, source: str) -> None:
    """Reject unknown keys and wrong value types instead of silently ignoring them.

    A typo such as ``test_in_canry`` or a string ``allow_unsafe_shell = "false"``
    would otherwise silently skip a gate or enable shell execution.
    """

    def fail(message: str) -> None:
        raise ConfigError(f"invalid pygate config in {source}: {message}")

    def check_keys(table: object, allowed: frozenset[str], where: str) -> dict:
        if not isinstance(table, dict):
            fail(f"{where} must be a table")
        unknown = sorted(set(table) - allowed)  # type: ignore[arg-type]
        if unknown:
            fail(f"unknown key(s) {unknown} in {where}; allowed: {sorted(allowed)}")
        return table  # type: ignore[return-value]

    top_where = "[tool.pygate]" if source.endswith("pyproject.toml") else "top level"
    if "tool" in user and not source.endswith("pyproject.toml"):
        fail("pygate.toml uses bare [policy]/[commands]/[gates] tables, not [tool.pygate.*]")
    check_keys(user, _TOP_LEVEL_KEYS, top_where)
    if "config_version" in user and not isinstance(user["config_version"], str):
        fail("config_version must be a string")
    if "allow_unsafe_shell" in user and not isinstance(user["allow_unsafe_shell"], bool):
        fail(f"allow_unsafe_shell must be a boolean (true/false), got {user['allow_unsafe_shell']!r}")
    for key, value in check_keys(user.get("policy", {}), frozenset(DEFAULT_POLICY), "policy").items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail(f"policy.{key} must be a number, got {value!r}")
    for key, value in check_keys(user.get("commands", {}), _GATE_NAMES, "commands").items():
        if isinstance(value, str):
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            fail(f"commands.{key} must be a string or a list of strings, got {value!r}")
    for key, value in check_keys(user.get("gates", {}), _GATES_KEYS, "gates").items():
        if not isinstance(value, bool):
            fail(f"gates.{key} must be a boolean (true/false), got {value!r}")


def _merge_config(user: dict, *, source: str) -> dict:
    _validate(user, source=source)
    defaults = _defaults()
    policy = {**defaults["policy"], **user.get("policy", {})}
    commands = user.get("commands", {})
    gates = {**defaults["gates"], **user.get("gates", {})}
    return {
        "config_version": user.get("config_version", CONFIG_VERSION),
        "policy": policy,
        "commands": commands,
        "gates": gates,
        "allow_unsafe_shell": bool(user.get("allow_unsafe_shell", False)),
        "source": source,
    }
