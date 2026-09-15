---
name: quick-gate-python
description: Use when you need a deterministic Python CI quality gate that normalizes Ruff, Pyright, and pytest results into one fail-fast decision, attempts bounded auto-repair, and escalates with machine-readable evidence for humans or agents when it cannot finish safely. A gate-and-escalate wrapper, not a lint dashboard.
license: MIT
compatibility: Requires Python 3.9+; installs via `pip install pygate-ci`, executable name is `pygate`. Also runnable standalone via `uvx --from pygate-ci pygate`. Runs the project's own Ruff/Pyright/pytest, no external network access required.
---

# quick-gate-python

quick-gate-python (PyPI package `pygate-ci`) is a deterministic Python CI
quality gate that normalizes Ruff, Pyright, and pytest results into one
fail-fast decision, attempts bounded auto-repair, and escalates with
machine-readable evidence for humans or agents when it cannot finish safely.
A gate-and-escalate wrapper, not a lint dashboard.

## Use it for

- Running Ruff + Pyright + pytest as one CI gate with a single stable JSON
  result
- Getting a content-hash-addressed snapshot digest and per-check argv/status
  detail an agent can parse deterministically
- Bounded, deterministic repair of common lint failures before escalating
- Summarizing a failed run into an agent-consumable brief

## Do not use it for

- A general-purpose linting dashboard or historical trend tracker
- Non-Python projects (use quick-gate-js for a Node-native gate)
- Unbounded auto-repair — repair attempts are capped by `--max-attempts`

## Quickstart

```bash
pip install pygate-ci
pygate run --mode canary --changed-files src/mymodule.py
```

Or without installing, via [uv](https://docs.astral.sh/uv/):

```bash
uvx --from pygate-ci pygate run --mode canary --changed-files src/mymodule.py
```

Real output from a run against a minimal file:

```json
{
  "schema": "gate-result/v1",
  "status": "pass",
  "snapshot_digest": "7a8e04e2feae6229d5ce67f7f78e649fd44caf8727e8ed9732f3f80b4311614d",
  "checked_paths": ["x = 1"],
  "checks": [
    {
      "name": "lint",
      "status": "pass",
      "argv": ["ruff", "check", "--no-cache", "--output-format", "json", "--exclude", ".pygate", "."]
    }
  ]
}
```

## Commands

```
pygate run --mode canary|full --changed-files <path>
pygate summarize --input <failures-json>
pygate repair --input <failures-json>
```

## Output shape

- `schema: gate-result/v1` — stable, versioned JSON schema
- `snapshot_digest` — content hash of the checked state, for caching/audit
- `checks[]` — one entry per underlying tool (`lint`, `typecheck`, `test`)
  with `name`, `status`, and the exact `argv` that was run
- `status`: `pass` or `fail` at the top level

## Common gotchas

- `--mode` accepts `canary` or `full` only — `quick` (used by the sibling
  quick-gate-js tool) is not a valid mode here.
- Executable is `pygate`, package name on PyPI is `pygate-ci` — `pip install
  quick-gate-python` will not find it.
- `checked_paths` echoes back file contents in some canary-mode runs on tiny
  fixtures, not just paths — read `checks[].argv` for the exact underlying
  tool invocation.

## More

Full docs and CI integration:
https://github.com/hermes-labs-ai/quick-gate-python
