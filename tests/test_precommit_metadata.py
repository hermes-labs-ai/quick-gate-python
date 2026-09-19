"""Contract tests for the native pre-commit hooks manifest.

Parses .pre-commit-hooks.yaml without a YAML dependency (the project's own
[dev] extra does not include pyyaml) by checking exact line content, since
the manifest is small and hand-authored.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_TEXT = (REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
MANIFEST_LINES = [line.rstrip("\n") for line in MANIFEST_TEXT.splitlines()]


def test_hooks_manifest_declares_canary_and_full_modes():
    assert MANIFEST_LINES.count("- id: pygate") == 1
    assert MANIFEST_LINES.count("- id: pygate-full") == 1

    assert "  entry: pygate run --mode canary" in MANIFEST_LINES
    assert "  entry: pygate run --mode full" in MANIFEST_LINES

    # Both hook blocks share the same shape.
    assert MANIFEST_LINES.count("  language: python") == 2
    assert MANIFEST_LINES.count("  pass_filenames: false") == 2
    assert MANIFEST_LINES.count("  always_run: true") == 2
    assert MANIFEST_LINES.count("  verbose: true") == 2


def test_hooks_manifest_is_valid_yaml_via_stdlib_json_incompatible_check():
    # No YAML parser dependency is available in this project's [dev] extra;
    # instead verify the file is non-empty, has no tabs (a common YAML
    # break), and every non-blank line is either a top-level '- id:' entry
    # or a two-space-indented 'key: value' line — the exact shape pre-commit
    # itself requires for a flat hooks list.
    assert MANIFEST_TEXT.strip()
    assert "\t" not in MANIFEST_TEXT
    for line in MANIFEST_LINES:
        if not line.strip():
            continue
        assert line.startswith("- id: ") or line.startswith("  "), line


def test_readme_documents_the_precommit_hook():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Pre-commit" in readme
    assert ".pre-commit-hooks.yaml" in readme
    assert "id: pygate" in readme
    assert "pre-commit run pygate" in readme


def test_both_hooks_install_the_gate_tools_they_shell_out_to():
    # Installing pygate brings its runtime deps (pydantic, tomli) only; Ruff,
    # Pyright, and pytest are [dev] extras and pre-commit's hook environment is
    # isolated, so without these the first run in a clean environment reports
    # every gate as "missing" (exit code 127) instead of gating anything.
    assert MANIFEST_LINES.count("    - ruff==0.16.8") == 2
    assert MANIFEST_LINES.count("    - pyright==1.1.414") == 2
    assert MANIFEST_LINES.count("    - pytest==9.1.1") == 1
    assert MANIFEST_LINES.count("    - pytest-json-report==1.5.0") == 1
    assert MANIFEST_LINES.count("  additional_dependencies:") == 2


def test_readme_documents_the_hook_dependencies():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for pin in ("ruff==0.16.8", "pyright==1.1.414", "pytest==9.1.1", "pytest-json-report==1.5.0"):
        assert pin in readme, f"README does not document the hook pin {pin!r}"
    # pre-commit replaces (never merges) the manifest list when a consumer sets
    # additional_dependencies, so the caller-owned case has to say so.
    assert "additional_dependencies" in readme
    assert "replaces" in readme


@pytest.mark.skipif(shutil.which("pre-commit") is None, reason="pre-commit is not installed")
def test_manifest_passes_precommits_own_validation():
    result = subprocess.run(
        ["pre-commit", "validate-manifest", str(REPO_ROOT / ".pre-commit-hooks.yaml")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
