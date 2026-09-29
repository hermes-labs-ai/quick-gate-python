"""Rollback must restore the workspace without destroying data the backup skipped."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from pygate.repair_command import _backup_workspace, _restore_workspace, execute_repair


def _make_project(root: Path, external: Path) -> None:
    (root / "app.py").write_text("import os\n")
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text("x = 1\n")
    # Names excluded from the backup at every depth.
    (root / "packages" / "web" / "dist").mkdir(parents=True)
    (root / "packages" / "web" / "dist" / "bundle.js").write_text("built\n")
    (root / "packages" / "web" / "node_modules" / "lib").mkdir(parents=True)
    (root / "packages" / "web" / "node_modules" / "lib" / "index.js").write_text("mod\n")
    (root / "vendor" / "sub" / ".git").mkdir(parents=True)
    (root / "vendor" / "sub" / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / "vendor" / "sub" / "f.txt").write_text("sub\n")
    # Symlinks: to an external directory and to a sibling file.
    external.mkdir()
    (external / "data.txt").write_text("shared\n")
    os.symlink(external, root / "shared")
    (root / "settings.ini").write_text("real\n")
    os.symlink("settings.ini", root / "settings_link.ini")


def _mutate(root: Path) -> None:
    (root / "app.py").write_text("")
    (root / "pkg" / "mod.py").unlink()
    (root / "pkg" / "new_by_fixer.py").write_text("y = 2\n")
    (root / "created_dir").mkdir()
    (root / "created_dir" / "junk.py").write_text("z = 3\n")


def _assert_restored(root: Path, external: Path) -> None:
    assert (root / "app.py").read_text() == "import os\n"
    assert (root / "pkg" / "mod.py").read_text() == "x = 1\n"
    assert not (root / "pkg" / "new_by_fixer.py").exists()
    assert not (root / "created_dir").exists()
    # Data the backup never copied must survive the rollback.
    assert (root / "packages" / "web" / "dist" / "bundle.js").read_text() == "built\n"
    assert (root / "packages" / "web" / "node_modules" / "lib" / "index.js").read_text() == "mod\n"
    assert (root / "vendor" / "sub" / ".git" / "HEAD").exists()
    assert (root / "vendor" / "sub" / "f.txt").read_text() == "sub\n"
    # Symlinks stay symlinks; the external target is untouched.
    assert (root / "shared").is_symlink()
    assert os.readlink(root / "shared") == str(external)
    assert (external / "data.txt").read_text() == "shared\n"
    assert (root / "settings_link.ini").is_symlink()
    assert os.readlink(root / "settings_link.ini") == "settings.ini"


def test_restore_preserves_skipped_dirs_and_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    external = tmp_path / "external"
    _make_project(root, external)
    backup = root / ".pygate" / "backup-attempt-1"
    _backup_workspace(root, backup)

    _mutate(root)
    _restore_workspace(root, backup)

    _assert_restored(root, external)


def test_repair_patch_budget_rollback_is_lossless(tmp_path: Path, seed_failures) -> None:
    failures_path = seed_failures(findings_count=1)
    root = tmp_path
    external = tmp_path.parent / f"{tmp_path.name}-external"
    _make_project(root, external)

    def fake_fix(*, cwd: Path, failures):
        _mutate(cwd)
        return [{"rule_id": "RUFF_AUTOFIX", "accepted": True}]

    snaps = iter([{}, {"app.py": 999}])
    with (
        patch("pygate.repair_command.run_deterministic_prefix", side_effect=fake_fix),
        patch("pygate.repair_command._diff_snapshot", side_effect=lambda cwd: next(snaps)),
    ):
        result = execute_repair(input_path=str(failures_path), max_attempts=3, cwd=root)

    assert result["reason_code"] == "PATCH_BUDGET_EXCEEDED"
    assert (root / ".pygate" / "escalation.json").exists()
    _assert_restored(root, external)
