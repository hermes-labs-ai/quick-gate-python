# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Updated Action pinning guidance after publication: `v0.2.1` is the first
  release tag containing the root `action.yml`; the audited commit remains
  the reproducible supply-chain pin.

## [0.2.1] - 2026-09-04

### Added

- Added `tests/test_fresh_repo_integration.py`, a real-subprocess fresh-repository proof: it
  builds throwaway projects from the existing `tests/action-fixture/` fixtures and runs the
  installed `pygate` binary (with real Ruff and Pyright, no mocked tool output) to demonstrate,
  end to end, that a clean project passes, a non-fixable type error fails the gate and repair
  correctly escalates, and a Ruff-fixable lint issue is auto-repaired back to a passing gate.
  Isolated behind a new `integration` pytest marker (`addopts = "-m 'not integration'"` in
  `pyproject.toml`) so it is excluded from the default `pytest` run and its "mocked tool output
  only" invariant. Run it explicitly with `pytest -m integration`.
- Added a `ci.yml` `integration` job that installs `.[dev]` (which supplies `pygate`, `ruff`,
  and `pyright` on `PATH`) and runs `pytest -m integration -v`, so the real-subprocess proof
  above runs on every push and pull request against `main`, alongside (not in place of) the
  existing offline `test` job and the GitHub-composite-action proof in `action-smoke.yml`.
- Added `tests/test_docs_action_pin.py`, a regression contract asserting that every documented
  root-action reference is a 40-character commit SHA and that all documented pins agree.

### Fixed

- Corrected the root-action pin in `llms.txt`, which still referenced the superseded `1a70edc`
  commit after the audited pin moved to `671e8db`.
- Replaced the "replace it with an immutable release tag when one exists" guidance in `README.md`,
  `SECURITY.md`, and `llms.txt`. The published `v0.1.0`, `v0.1.1`, and `v0.2.0` tags predate the
  root `action.yml`, so following that guidance produced a workflow that cannot resolve the action.

### Boundaries

- This release does not change any gate, repair, or CLI behavior; the package version moves only
  because CI now runs an additional, previously-unwired proof and the docs/pin corrections above
  ship with it. It does not by itself change root-action pinning guidance: continue to pin the
  root action at an audited commit, not at a PyPI release tag, until the README's "Pinning
  policy" section is updated to name a tag cut at or after `action.yml` landed.

## [0.2.0] - 2026-08-08

### Added

- Added the side-effect-free `pygate.api.evaluate` primitive with argv-safe command execution, bounded timeouts, capped output, snapshot binding, and the `gate-result/v1` contract.
- Added explicit CLI artifact output via `--output-dir`; `pygate run` without it emits JSON without creating worktree state.

### Changed

- Standardized the cross-engine discriminator as `"schema": "gate-result/v1"` and aligned result/check status enums with QuickGate.js and HermesGate.
- Made `--changed-files` optional for whole-project runs and made the composite action install its checked-out source instead of a registry version.

## [0.1.2] - 2026-05-30

### Changed

- Updated project metadata: copyright holder, maintainer contact, and citation files.

## [0.1.1] - 2026-03-02

### Fixed

- Standardized copyright to Hermes Labs in LICENSE
- Fixed stale GitHub URLs (hermes-labs-ai/pygate → hermes-labs-ai/quick-gate-python)
- Added PyPI version badge to README

## [0.1.0] - 2026-02-23

### Added

- `pygate run` command with canary and full modes
- Lint gate via ruff with JSON output parsing
- Type-check gate via pyright with JSON output parsing
- Test gate via pytest with json-report plugin
- `pygate summarize` command producing agent-friendly briefs (JSON + Markdown)
- `pygate repair` command with bounded deterministic repair loop
- Deterministic fixes: `ruff check --fix` + `ruff format` on scoped files
- Repair safeguards: workspace backup/restore, patch budget, no-improvement abort, time cap
- 7 escalation reason codes with structured evidence
- Rich environment metadata capture (Python version, platform, venv, resolver, packages)
- Configuration via `pygate.toml` or `[tool.pygate]` in `pyproject.toml`
- Composite GitHub Action for CI integration
- Structured artifacts: failures.json, run-metadata.json, agent-brief.json/md, repair-report.json, escalation.json

[Unreleased]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hermes-labs-ai/quick-gate-python/releases/tag/v0.1.0
