# Quick Gate Python (pygate-ci)

Deterministic quality gate CLI for Python projects. Runs ruff + pyright + pytest, produces structured JSON artifacts, supports bounded auto-repair.

## Commands

- `pip install -e ".[dev]"` -- Install
- `pytest` -- offline suite (mocked gate outputs); excludes `integration`-marked tests
- `pytest -m integration` -- real fresh-repository proof; runs the packaged `pygate` binary plus ruff/pyright against on-disk fixtures, opt-in and requires those tools on PATH
- `pytest tests/test_run_command.py -v` -- Single module
- `ruff check src/pygate/ --fix` -- Lint fix
- `pyright src/pygate/` -- Type check
- `python -m build` -- Build

## Architecture

Three subcommands: `pygate run` (execute gates) → `pygate repair` (auto-fix loop) → `pygate summarize` (agent brief).

```
src/pygate/
  cli.py → run_command.py / repair_command.py / summarize_command.py
  gates/ruff.py, pyright.py, pytest_gate.py  # Individual gates
  models.py         # Pydantic v2 models for all structured output
  config.py         # Config from pygate.toml or pyproject.toml
  exec.py           # Subprocess wrapper
  deterministic_fix.py  # ruff --fix with rollback safety
```

Key flow: `run_command` calls each gate → gate parses tool JSON output → results written as artifacts → exit code reflects pass/fail.

## Key Constraints

- Pydantic v2 for all models (not dataclasses)
- `from __future__ import annotations` in every module
- JSON schemas in `schemas/` must match Pydantic models
- Tests never execute real subprocesses — all gate outputs mocked, except the explicitly opt-in `integration`-marked tests (`tests/test_fresh_repo_integration.py`), which are excluded from the default `pytest` run
- Repair loop is bounded by `--max-attempts` (safety invariant)
- Two runtime deps only: `pydantic`, `tomli` (for Python <3.11)

## Gotchas

- Package name on PyPI is `pygate-ci` but import name is `pygate`
- `hatchling` build system (not setuptools) — source lives in `src/pygate/`
- `pytest_gate.py` (not `test_gate.py`) to avoid pytest collecting it as a test
- Config loading checks `pygate.toml` first, falls back to `[tool.pygate]` in `pyproject.toml`
- `deterministic_fix.py` creates backup before `ruff --fix` and rolls back on failure
