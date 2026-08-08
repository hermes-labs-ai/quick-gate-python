# PyGate

[![CI](https://github.com/hermes-labs-ai/quick-gate-python/actions/workflows/ci.yml/badge.svg)](https://github.com/hermes-labs-ai/quick-gate-python/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pygate-ci)](https://pypi.org/project/pygate-ci/)
[![Apache 2.0 license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

**PyGate turns Ruff, Pyright, and pytest results into one deterministic Python quality-gate result, with bounded lint repair and structured evidence when the gate cannot finish.**

Python maintainers usually meet the same problem at the worst possible time: a pull request has several tool outputs, each with its own format and failure order, and someone must decide what to fix first. PyGate gives a CI job or follow-up agent one fail-fast result, preserves the underlying command evidence, and stops deterministic repair within an explicit budget.

## First success

PyGate is published as `pygate-ci` and installs the `pygate` command. It supports Python 3.10 and newer. Install PyGate and the tools used by the default gates:

~~~bash
python -m pip install pygate-ci ruff pyright pytest pytest-json-report
~~~

Create a changed-file list from the current Git diff, then run a canary gate:

~~~bash
git diff --name-only HEAD^ > /tmp/pygate-changed-files.txt
pygate run --mode canary --changed-files /tmp/pygate-changed-files.txt
~~~

The command prints a JSON `gate-result/v1` result. With no `--output-dir`, it does not create `.pygate` or other files. `canary` runs Ruff and Pyright; `full` also runs pytest.

For a file-backed CI result, choose the output directory explicitly:

~~~bash
pygate run \
  --mode full \
  --changed-files /tmp/pygate-changed-files.txt \
  --output-dir .pygate
~~~

The most useful next command after a failed run is:

~~~bash
pygate summarize --input .pygate/failures.json
~~~

That writes a short agent brief to `.pygate/agent-brief.json` and `.pygate/agent-brief.md`.

## What PyGate does

PyGate coordinates three existing tools:

| Gate | Default command | Canary | Full |
| --- | --- | --- | --- |
| Lint | `ruff check --output-format json --exclude .pygate .` | Yes | Yes |
| Type check | `pyright --outputjson .` | Yes | Yes |
| Tests | `pytest -q` without artifacts; JSON-report mode with an explicit output directory | No, unless configured | Yes |

The default commands scan the configured project command. `--changed-files` identifies the paths whose bytes are snapshotted and recorded in the result; it does not, by itself, rewrite the default Ruff or Pyright commands into changed-file-only analysis. Configure commands explicitly when a repository needs narrower scope.

The flow is intentionally small:

1. Load `pygate.toml` or `[tool.pygate]` from `pyproject.toml`.
2. Run the configured or default gate commands with bounded time and output capture.
3. Normalize Ruff, Pyright, and pytest findings and bind the result to input snapshots.
4. Return a pass, fail, timeout, or error result.
5. Optionally run a bounded deterministic repair loop for Ruff-fixable findings.

PyGate does not replace Ruff, Pyright, or pytest. It gives their results a predictable decision and evidence shape for a human or an automation layer.

## CLI

~~~text
pygate --version
pygate run --mode canary|full --changed-files <path> [--output-dir <directory>] [--unsafe-shell]
pygate summarize --input <failures.json>
pygate repair --input <failures.json> [--max-attempts N]
~~~

`--changed-files` accepts either one path per line or a JSON array of strings. Relative paths are resolved from the current working directory.

Exit codes are:

- `pygate run`: `0` for pass; `1` for fail or timeout.
- `pygate summarize`: `0` after writing the brief.
- `pygate repair`: `0` when repair passes; `2` when it escalates.

### Output and artifacts

There are two intentionally different run paths:

- **Current CLI path:** `pygate run` without `--output-dir` prints the contract JSON and is side-effect-free with respect to project files.
- **Explicit artifact path:** `pygate run --output-dir DIR` creates `DIR` and writes `failures.json`, `run-metadata.json`, and `gate-result.json` there. A default full-mode pytest command also writes `pytest-report.json` there.
- **Legacy artifact commands:** `pygate summarize` and `pygate repair` use `.pygate/` in the current working directory for their outputs. `pygate repair` may modify eligible Python files while applying Ruff fixes; it writes `repair-report.json` on repair success or `escalation.json` when it stops without passing.

Important artifact files include:

| File | Purpose |
| --- | --- |
| `gate-result.json` | Versioned gate result from an explicit `run --output-dir` |
| `failures.json` | Normalized findings and gate statuses |
| `run-metadata.json` | Environment and command traces, including timeouts and truncation |
| `agent-brief.json` / `agent-brief.md` | Prioritized follow-up actions from `summarize` |
| `repair-report.json` | Bounded repair attempts when repair passes |
| `escalation.json` | Reason and evidence when repair escalates |

The repository includes sample artifacts in [`demo/artifacts/`](demo/artifacts/) and JSON Schemas in [`schemas/`](schemas/).

### The `gate-result/v1` contract

The `gate-result/v1` JSON contract is the stable result boundary exposed by the side-effect-free API and the CLI's no-output-directory path. It includes:

- `schema`, `status`, and the canonical `checked_paths`;
- per-check status, argv, exit code, duration, captured output, and diagnostics;
- normalized `findings` plus command versions;
- snapshot digests, configuration identity/digest, package version, elapsed time, and truncation/error state.

The contract describes what these configured local checks observed. It is not a universal correctness proof, a security verdict, or a guarantee that a repository is safe to merge.

## Embeddable Python API

Use `pygate.api.evaluate` when the caller needs the result in memory and does not want PyGate to create files or mutate environment state:

~~~python
from pathlib import Path

from pygate.api import evaluate
from pygate.models import RunMode

result = evaluate(
    mode=RunMode.CANARY,
    checked_paths=["src/app.py"],
    cwd=Path.cwd(),
)

print(result.schema)  # gate-result/v1
print(result.status)  # pass, fail, timeout, or error
~~~

The API returns a Pydantic `GateResultV1` model. It does not write `.pygate`, `gate-result.json`, or other artifacts. Use the explicit CLI output path or the legacy artifact commands when files are required.

## Bounded repair

`pygate repair` is deliberately narrower than an AI coding agent. For Ruff findings in eligible Python files, it can run `ruff check --fix` and `ruff format`, re-run the gates, and stop when the result passes, worsens, exceeds the patch budget, reaches the attempt limit, or stops improving.

The default policy is:

| Policy | Default |
| --- | ---: |
| Maximum attempts | 3 |
| Maximum patch lines | 150 |
| No-improvement abort | 2 consecutive attempts |
| Overall time cap | 1,200 seconds |

Repair does not invent semantic fixes for type errors or failing tests. Review any file changes before accepting them.

## Configuration

PyGate reads `pygate.toml` first. If that file is absent, it reads `[tool.pygate]` from `pyproject.toml`.

~~~toml
[tool.pygate]
allow_unsafe_shell = false

[tool.pygate.policy]
max_attempts = 3
max_patch_lines = 150
abort_on_no_improvement = 2
time_cap_seconds = 1200
command_timeout_seconds = 120
gate_timeout_seconds = 600
output_cap_bytes = 1048576

[tool.pygate.commands]
lint = "ruff check --output-format json --exclude .pygate ."
typecheck = "pyright --outputjson ."
test = "pytest --json-report --json-report-file=.pygate/pytest-report.json -q"

[tool.pygate.gates]
test_in_canary = false
~~~

The same keys can be used in a standalone `pygate.toml` with `[policy]`, `[commands]`, and `[gates]` sections. String commands are tokenized into argv-safe arguments by default, so shell metacharacters remain data. `--unsafe-shell` or `allow_unsafe_shell = true` is an explicit compatibility escape hatch for legacy shell command strings. Review those commands as executable code.

## GitHub Actions

The repository ships a composite action at [`.github/actions/pygate/action.yml`](.github/actions/pygate/action.yml) and a copyable example at [`.github/workflows/example-usage.yml`](.github/workflows/example-usage.yml):

~~~yaml
name: PyGate

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write # only needed when post-comment is true

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: hermes-labs-ai/quick-gate-python/.github/actions/pygate@main
        with:
          mode: canary
          repair: "true"
          max-attempts: 3
          python-version: "3.12"
          post-comment: "true"
~~~

The action installs `pygate-ci`, Ruff, and Pyright, detects changed files, writes run artifacts to `.pygate/`, optionally attempts repair, optionally posts a pull-request comment, and uploads the artifact directory. Canary mode skips tests by default. To use full mode with the default test command, make `pytest` and `pytest-json-report` available in the action environment; the composite action does not install those two packages itself.

PyGate never grants merge authority. A workflow still decides whether a failed, timed-out, or escalated job blocks a pull request, and any comment or artifact should be treated as untrusted command output before security-sensitive rendering.

## Privacy, egress, and safety

- PyGate itself does not make network requests or silently install packages.
- It executes the configured local commands for Ruff, Pyright, and pytest. Those tools may have their own network or plugin behavior; review their configuration and dependency policy.
- Command stdout and stderr can be copied into artifacts. Treat `.pygate/` as project data, not as a trusted security report.
- The repair loop reads and writes eligible files in the current project and keeps backups while it works. Run it on a clean branch or review the resulting diff.
- Custom commands and `--unsafe-shell` can execute arbitrary commands. Do not enable them for untrusted configuration without review.
- The GitHub Action needs only `contents: read` for its normal work. Pull-request comments require `pull-requests: write`.

## Limitations

PyGate does not promise:

- a proof of universal correctness or a complete quality audit;
- a security guarantee, vulnerability scan, or safe-to-merge verdict;
- semantic repair for type errors, test failures, or architectural changes;
- automatic merge authority or approval of a pull request;
- changed-file-only analysis unless the configured underlying commands implement that scope;
- support for every project layout or monorepo workflow;
- zero network activity from the underlying tools it invokes.

The default integration is intentionally narrow: Ruff linting, Pyright type checking, and pytest testing, with deterministic parsing and bounded repair around them.

## Troubleshooting

**`ruff` or `pyright` is missing.** Install the underlying tools in the same environment as `pygate`:

~~~bash
python -m pip install ruff pyright
~~~

**Full mode cannot run pytest.** Install both pytest and the JSON-report plugin, or configure a test command that emits output PyGate can consume:

~~~bash
python -m pip install pytest pytest-json-report
~~~

**No artifacts appeared.** That is expected for `pygate run` without `--output-dir`. Use `--output-dir .pygate` for run artifacts. `summarize` and `repair` retain their `.pygate/` compatibility behavior.

**A custom command behaves differently than a shell command.** Commands are argv-tokenized by default. If legacy shell syntax is unavoidable, pass `--unsafe-shell` or set `allow_unsafe_shell = true` only after reviewing the command.

**The gate fails after a file changes during execution.** PyGate compares snapshots before and after the run and reports the result as stale. Re-run after the writer has stopped.

## Development and contribution

For a local development checkout:

~~~bash
git clone https://github.com/hermes-labs-ai/quick-gate-python.git
cd quick-gate-python
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
ruff format --check src/ tests/
pyright src/
~~~

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidance and [`SECURITY.md`](SECURITY.md) for vulnerability reporting and execution-safety notes.

## License

PyGate is licensed under the [Apache License 2.0](LICENSE).
