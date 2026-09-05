# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in PyGate, please report it responsibly.

**Do not open a public issue.**

Instead, email **rbosch@lpci.ai** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact assessment

You will receive an acknowledgment within 48 hours. We aim to provide a fix or mitigation plan within 7 days of confirmation.

## Scope

PyGate executes external tools (`ruff`, `pyright`, `pytest`) via subprocess. Security considerations include:

### Command Execution

- **Configured commands**: By default, command strings from `[commands]` in `pygate.toml` or `[tool.pygate.commands]` in `pyproject.toml` are tokenized into argv-safe arguments. `--unsafe-shell` or `allow_unsafe_shell = true` is an explicit compatibility escape hatch that executes command text through a shell; review custom command overrides carefully.
- **File path sanitization**: File paths passed to repair commands are escaped with `shlex.quote()` to prevent shell injection via crafted filenames. Paths containing `..` or absolute paths are rejected by the repair scope filter.

### File System Access

- The repair loop reads and writes files within the project directory. It does not access files outside the working directory.
- Workspace backups use `shutil.copytree` with `symlinks=True` to preserve symlink targets without following them outside the tree.
- Excluded directories (`.git`, `.venv`, `__pycache__`, `node_modules`, etc.) are never modified by the repair loop.

### Network Access

- PyGate itself does not make network requests. All operations are local.
- The tools it invokes (`ruff`, `pyright`, `pytest`) may make network requests depending on their own configuration (e.g., pyright downloading typestubs).

### GitHub Actions Composite Action

- **Input validation**: The root Marketplace action validates `mode`, the repair/comment/fail-on-error booleans, `max-attempts` from 1 through 10, and supplied changed-file content before running gates. Inputs are passed via environment variables rather than string interpolation to prevent injection.
- **Action defaults**: The root Marketplace action defaults to `repair: false` and `post-comment: false`. Enabling repair is an explicit opt-in that may modify eligible files in the consumer workspace; enabling comments is an explicit opt-in that requires `pull-requests: write`.
- **Supply chain pinning**: All third-party actions in CI workflows and the composite action are pinned to SHA digests with version comments (e.g., `actions/checkout@<sha> # v4`). This prevents compromised upstream tags from injecting malicious code.
- **Permissions**: The composite action requires only `contents: read` by default. The optional PR comment feature requires `pull-requests: write`. No other permissions are requested.
- **Full-mode dependencies**: The caller owns project and test dependencies. Before full mode, the caller must make `pytest` and `pytest-json-report` available in the Python version selected by the action; the action preflights them and does not install them.
- **Action pinning**: Use the root `hermes-labs-ai/quick-gate-python@39b27c74fa5934c21d4068f3aee06c766e8899ba` audited commit for an immutable reference. `v0.2.1` is the first valid release-tag reference for the root action; `v0.1.0`, `v0.1.1`, and `v0.2.0` predate `action.yml` and do not resolve. Do not use a mutable branch reference.
- **Artifact trust**: Artifacts uploaded to `.pygate/` contain command output (stdout/stderr) from the target project. Downstream consumers should treat these as untrusted data and validate before rendering in security-sensitive contexts.

### Dependency Supply Chain

- PyGate's runtime dependencies are limited to `pydantic>=2` and `tomli>=2` (Python < 3.11 only).
- Development dependencies (`ruff`, `pyright`, `pytest`) are not runtime requirements.
- Dependabot is configured to monitor both pip and GitHub Actions dependencies for security updates.
