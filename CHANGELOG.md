# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `tests/test_docs_action_pin.py`, a regression contract asserting that every documented
  root-action reference is a 40-character commit SHA and that all documented pins agree.

### Fixed

- Corrected the root-action pin in `llms.txt`, which still referenced the superseded `1a70edc`
  commit after the audited pin moved to `671e8db`.
- Replaced the "replace it with an immutable release tag when one exists" guidance in `README.md`,
  `SECURITY.md`, and `llms.txt`. The published `v0.1.0`, `v0.1.1`, and `v0.2.0` tags predate the
  root `action.yml`, so following that guidance produced a workflow that cannot resolve the action.

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

[Unreleased]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/hermes-labs-ai/quick-gate-python/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hermes-labs-ai/quick-gate-python/releases/tag/v0.1.0
