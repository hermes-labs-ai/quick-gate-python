# AGENTS.md

PyGate is a deterministic Python CI gate that wraps Ruff, Pyright, and pytest and can escalate with structured evidence.

## Use it for

- running one fail-fast gate over Python lint, typecheck, and test output
- generating machine-readable artifacts for follow-up agents or humans
- attempting bounded deterministic repair before escalating

## Do not use it for

- replacing Ruff, Pyright, or pytest
- unbounded auto-fixing
- semantic code repair beyond deterministic lint-safe edits

## Minimal commands

```bash
pip install -e ".[dev]"
pygate --help
pygate summarize --input demo/artifacts/failures.json
pytest -q
pytest -m integration  # real fresh-repository proof; needs pygate/ruff/pyright on PATH
ruff check src/ tests/
pyright src/
```

## Output shape

- `pygate run`: writes `.pygate/failures.json` and `.pygate/run-metadata.json`
- `pygate summarize`: writes `.pygate/agent-brief.json` and `.pygate/agent-brief.md`
- `pygate repair`: writes `.pygate/repair-report.json` or `.pygate/escalation.json`

## Success means

- gate results are normalized into a stable schema
- deterministic repair stops within the configured budget
- escalation artifacts explain what blocked automatic completion

## Common failure cases

- required underlying tools are not installed in the target environment
- users expect PyGate to invent fixes for semantic failures
- downstream automation ignores the escalation codes and retries blindly

## Maintainer notes

- keep artifact schemas aligned with the Pydantic models
- keep the repair loop bounded and explicit
- keep CLI examples in README runnable against demo artifacts
