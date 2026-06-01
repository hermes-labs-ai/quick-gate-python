# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

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

- **Shell commands**: PyGate constructs shell commands from configuration values. The `[commands]` section in `pygate.toml` or `[tool.pygate.commands]` in `pyproject.toml` is executed via `subprocess.run(shell=True)`. Users should review custom command overrides carefully, as they are passed directly to the shell.
- **File path sanitization**: File paths passed to repair commands are escaped with `shlex.quote()` to prevent shell injection via crafted filenames. Paths containing `..` or absolute paths are rejected by the repair scope filter.

### File System Access

- The repair loop reads and writes files within the project directory. It does not access files outside the working directory.
- Workspace backups use `shutil.copytree` with `symlinks=True` to preserve symlink targets without following them outside the tree.
- Excluded directories (`.git`, `.venv`, `__pycache__`, `node_modules`, etc.) are never modified by the repair loop.

### Network Access

- PyGate itself does not make network requests. All operations are local.
- The tools it invokes (`ruff`, `pyright`, `pytest`) may make network requests depending on their own configuration (e.g., pyright downloading typestubs).

### GitHub Actions Composite Action

- **Input validation**: The composite action validates the `mode` input against an allowlist (`canary` or `full`) before passing it to the CLI. The `max-attempts` input is passed through to the CLI's argparse, which validates it as an integer; negative values are not rejected at the action layer. All inputs are passed via environment variables rather than string interpolation to prevent injection.
- **Supply chain pinning**: All third-party actions in CI workflows and the composite action are pinned to SHA digests with version comments (e.g., `actions/checkout@<sha> # v4`). This prevents compromised upstream tags from injecting malicious code.
- **Permissions**: The composite action requires only `contents: read` by default. The optional PR comment feature requires `pull-requests: write`. No other permissions are requested.
- **Artifact trust**: Artifacts uploaded to `.pygate/` contain command output (stdout/stderr) from the target project. Downstream consumers should treat these as untrusted data and validate before rendering in security-sensitive contexts.

### Dependency Supply Chain

- PyGate's runtime dependencies are limited to `pydantic>=2` and `tomli>=2` (Python < 3.11 only).
- Development dependencies (`ruff`, `pyright`, `pytest`) are not runtime requirements.
- Dependabot is configured to monitor both pip and GitHub Actions dependencies for security updates.
