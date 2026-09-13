---
name: quick-gate-python
description: Run the deterministic PyGate quality gate (Ruff, Pyright, pytest) on a Python repository and report its gate-result/v1 outcome accurately. Trigger when the user asks to gate, lint-and-typecheck-and-test, or check the CI quality status of a Python project before handing work off.
---

PyGate (PyPI package `pygate-ci`, command `pygate`) runs Ruff, Pyright, and
pytest and turns their output into one deterministic `gate-result/v1` JSON
result. PyGate itself makes no network requests and installs nothing
(https://github.com/hermes-labs-ai/quick-gate-python).

1. Pick a runner: if `pygate --version` works, use the bare `pygate` command
   below. Otherwise use `uvx --from pygate-ci==0.3.1 pygate` (zero-install).
   Keep the exact version pin so it does not fetch an unreviewed newer
   release, and keep using the runner you picked for every later step.
2. PyGate does not bundle the tools it gates. Confirm `ruff` and `pyright`
   run in the project's environment (and `pytest` plus `pytest-json-report`
   for full mode). If one is missing, tell the user which one; do not install
   packages into their environment without asking.
3. From the repository root, run the side-effect-free canary gate (Ruff and
   Pyright); it prints JSON and writes no files:
   ```
   pygate run --mode canary
   ```
   Use `--mode full` to include pytest. Only when the user wants artifacts on
   disk, add `--output-dir .pygate`, then `pygate summarize --input
   .pygate/failures.json` writes `.pygate/agent-brief.md`.
4. Read the result, not just the exit code (`0` pass, `1` fail or timeout):
   report the top-level `status`, each check's status, and the first few
   `findings` with file, line, and message.

Constraints:
- Report only what the configured checks observed. A pass is not a proof of
  correctness, a security verdict, or approval to merge.
- A missing tool, timeout, stale snapshot, or error is not a pass; say so.
- Do not run `pygate repair` or `--unsafe-shell` unless the user asks. Repair
  edits files with Ruff fixes only and escalates (exit `2`) on anything else;
  run it on a clean branch and show the resulting diff.
- Command output can contain project data; do not paste it anywhere the user
  has not asked for.
