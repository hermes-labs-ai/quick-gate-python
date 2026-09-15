"""Contract tests for the native pre-commit hooks manifest.

Parses .pre-commit-hooks.yaml without a YAML dependency (the project's own
[dev] extra does not include pyyaml) by checking exact line content, since
the manifest is small and hand-authored.
"""

from __future__ import annotations

from pathlib import Path

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
