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


def _merge_config(user: dict, *, source: str) -> dict:
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
