"""Contract tests for the native pre-commit hooks manifest."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))


def test_hooks_manifest_declares_canary_and_full_modes():
    assert len(HOOKS) == 2
    by_id = {hook["id"]: hook for hook in HOOKS}

    assert set(by_id) == {"pygate", "pygate-full"}

    canary = by_id["pygate"]
    assert canary["entry"] == "pygate run --mode canary"
    assert canary["language"] == "python"
    assert canary["pass_filenames"] is False
    assert canary["always_run"] is True
    assert canary["verbose"] is True

    full = by_id["pygate-full"]
    assert full["entry"] == "pygate run --mode full"
    assert full["language"] == "python"
    assert full["pass_filenames"] is False
    assert full["always_run"] is True
    assert full["verbose"] is True


def test_readme_documents_the_precommit_hook():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Pre-commit" in readme
    assert ".pre-commit-hooks.yaml" in readme
    assert "id: pygate" in readme
    assert "pre-commit run pygate" in readme
