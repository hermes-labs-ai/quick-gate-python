# Contributing to PyGate

Thank you for your interest in contributing to PyGate! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10+
- [ruff](https://docs.astral.sh/ruff/installation/) (for linting)
- [pyright](https://github.com/microsoft/pyright) (for type checking)
- [pytest](https://docs.pytest.org/) (for testing)

### Install

```bash
git clone https://github.com/hermes-labs-ai/quick-gate-python.git
cd quick-gate-python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
```

### Run Linting

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

### Run Type Checking

```bash
pyright src/
```

## Making Changes

1. **Fork the repository** and create a feature branch from `main`.
2. **Write tests** for any new functionality or bug fixes.
3. **Follow existing code style** — the project uses ruff for formatting and linting.
4. **Keep commits focused** — one logical change per commit.
5. **Update CHANGELOG.md** under the `[Unreleased]` section.

## Pull Request Process

1. Ensure all tests pass (`pytest tests/ -v`).
2. Ensure linting passes (`ruff check src/ tests/`).
3. Update documentation if your change affects user-facing behavior.
4. Fill out the PR template with a clear description of your changes.
5. Request a review.

## Code Architecture

```
src/pygate/
├── cli.py                  # Argparse CLI entrypoint
├── models.py               # All Pydantic v2 models (single source of truth)
├── constants.py            # Directory paths, policy defaults, escalation codes
├── config.py               # Load pygate.toml / pyproject.toml config
├── exec.py                 # Subprocess wrapper → CommandTrace
├── env.py                  # Environment detection (Python, platform, packages)
├── fs.py                   # File utilities (JSON read/write, changed files)
├── gates/
│   ├── __init__.py         # Gate orchestrator
│   ├── ruff.py             # Ruff lint output parser
│   ├── pyright.py          # Pyright typecheck output parser
│   └── pytest_gate.py      # Pytest json-report parser
├── run_command.py          # `pygate run` implementation
├── summarize_command.py    # `pygate summarize` implementation
├── repair_command.py       # `pygate repair` bounded loop
└── deterministic_fix.py    # ruff --fix + format strategies
```

Key principles:

- **Pydantic models are the schema** — models in `models.py` are the single source of truth. JSON Schema files in `schemas/` are generated from these models for downstream validation and code generation.
- **Deterministic only (v1)** — no model-assisted or AI-powered repairs.
- **Structured artifacts** — every operation produces machine-readable JSON. See `demo/artifacts/` for sample output.

### Evaluation Suite

The `eval/` directory contains a real-world evaluation suite with 8 scenarios:

```bash
python eval/run_eval.py
```

This requires `pygate`, `ruff`, `pyright`, and `pytest` (with `pytest-json-report`) to be installed and on PATH.

## Reporting Issues

- Use the [bug report template](https://github.com/hermes-labs-ai/quick-gate-python/issues/new?template=bug_report.yml) for bugs.
- Use the [feature request template](https://github.com/hermes-labs-ai/quick-gate-python/issues/new?template=feature_request.yml) for ideas.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
