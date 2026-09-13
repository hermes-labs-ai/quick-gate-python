"""The repository root is one portable Agent Plugin with one canonical skill.

  plugin.json                        Agent Plugins 1.0.0 manifest (read by Codex CLI)
  .claude-plugin/plugin.json         Claude Code plugin manifest
  .claude-plugin/marketplace.json    Claude Code marketplace, source "."
  .agents/plugins/marketplace.json   Codex repo marketplace, source "./"
  gemini-extension.json              Gemini CLI extension manifest

Every manifest resolves the repository root, whose only skill is
``skills/quick-gate-python/SKILL.md``. No host may carry its own copy.

The live install tests are ``integration``-marked (they run real host CLIs in an
isolated HOME) and skip when the host CLI is not installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "quick-gate-python"
PORTABLE_MANIFEST = ROOT / "plugin.json"
CLAUDE_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
CLAUDE_MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
GEMINI_MANIFEST = ROOT / "gemini-extension.json"
CANONICAL_SKILL = ROOT / "skills" / PLUGIN_NAME / "SKILL.md"
SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PORTABLE_KEYS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
SKIPPED_DIRS = {".git", ".venv", "venv", "node_modules", ".pytest_cache", ".ruff_cache", "dist", "build"}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pyproject_field(name: str) -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match, f"{name} not found in pyproject.toml"
    return match.group(1)


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    assert match, f"{path} has no YAML frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_portable_manifest_follows_agent_plugins_schema() -> None:
    manifest = _json(PORTABLE_MANIFEST)
    assert manifest["$schema"] == SCHEMA_ID
    assert manifest["name"] == PLUGIN_NAME
    assert set(manifest) <= PORTABLE_KEYS, set(manifest) - PORTABLE_KEYS
    assert set(manifest.get("author", {})) <= {"name", "email", "url"}


def test_manifest_identity_matches_the_release() -> None:
    version, description = _pyproject_field("version"), _pyproject_field("description")
    for path in (PORTABLE_MANIFEST, CLAUDE_MANIFEST, GEMINI_MANIFEST):
        manifest = _json(path)
        assert manifest["name"] == PLUGIN_NAME, path
        assert manifest["version"] == version, path
        assert manifest["description"] == description, path
    portable, claude = _json(PORTABLE_MANIFEST), _json(CLAUDE_MANIFEST)
    for key in ("author", "homepage", "repository", "license"):
        assert portable[key] == claude[key], key


def test_marketplaces_resolve_to_the_repository_root() -> None:
    claude = _json(CLAUDE_MARKETPLACE)
    (claude_entry,) = claude["plugins"]
    assert claude["name"] == claude_entry["name"] == PLUGIN_NAME
    assert claude_entry["source"] == "."
    assert (CLAUDE_MARKETPLACE.parents[1] / claude_entry["source"]).resolve() == ROOT

    codex = _json(CODEX_MARKETPLACE)
    (codex_entry,) = codex["plugins"]
    assert codex["name"] == codex_entry["name"] == PLUGIN_NAME
    assert codex_entry["source"] == {"source": "local", "path": "./"}
    assert (CODEX_MARKETPLACE.parents[2] / codex_entry["source"]["path"]).resolve() == ROOT


def test_every_manifest_resolves_the_single_canonical_skill() -> None:
    skills = sorted(
        path.relative_to(ROOT)
        for path in ROOT.rglob("SKILL.md")
        if not SKIPPED_DIRS.intersection(path.relative_to(ROOT).parts)
    )
    assert skills == [CANONICAL_SKILL.relative_to(ROOT)], skills
    assert sorted(p.name for p in (ROOT / "skills").iterdir()) == [PLUGIN_NAME]
    frontmatter = _frontmatter(CANONICAL_SKILL)
    assert frontmatter["name"] == PLUGIN_NAME
    assert frontmatter["description"]
    for manifest in (PORTABLE_MANIFEST, CLAUDE_MANIFEST, GEMINI_MANIFEST):
        assert "skills" not in _json(manifest), f"{manifest} must use the default skills/ directory"
    for extra in (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills", ROOT / ".gemini", ROOT / ".codex-plugin"):
        assert not extra.exists(), f"{extra} would be a second, driftable skill surface"


def test_skill_pins_the_released_runner() -> None:
    text = CANONICAL_SKILL.read_text(encoding="utf-8")
    assert f"uvx --from pygate-ci=={_pyproject_field('version')} pygate" in text


def test_documented_gemini_install_pins_a_ref() -> None:
    """Releases up to v0.3.1 predate gemini-extension.json, so an unpinned install fails."""
    commands = re.findall(
        r"gemini extensions install https://github\.com/hermes-labs-ai/quick-gate-python[^\n`|]*",
        (ROOT / "README.md").read_text(encoding="utf-8"),
    )
    assert commands, "README.md no longer documents the Gemini install"
    for command in commands:
        assert "--ref " in command, command


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / PLUGIN_NAME
    pkg.mkdir()
    for rel in ("plugin.json", "gemini-extension.json"):
        shutil.copy2(ROOT / rel, pkg / rel)
    for rel in (".agents", ".claude-plugin", "skills"):
        shutil.copytree(ROOT / rel, pkg / rel)
    return pkg


def _run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, env=env, timeout=180)


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
def test_codex_marketplace_install_reads_back_the_skill(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    env = {"HOME": str(home), "CODEX_HOME": str(home / ".codex"), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}

    add = _run(["codex", "plugin", "marketplace", "add", str(pkg)], env)
    assert add.returncode == 0, f"{add.stdout}\n{add.stderr}"
    install = _run(["codex", "plugin", "add", f"{PLUGIN_NAME}@{PLUGIN_NAME}"], env)
    assert install.returncode == 0, f"{install.stdout}\n{install.stderr}"
    listed = _run(["codex", "plugin", "list"], env)
    assert any(line.startswith(f"{PLUGIN_NAME}@{PLUGIN_NAME}") for line in listed.stdout.splitlines()), listed.stdout
    installed = list((home / ".codex" / "plugins").rglob(f"skills/{PLUGIN_NAME}/SKILL.md"))
    assert installed and all(path.read_bytes() == CANONICAL_SKILL.read_bytes() for path in installed)


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("gemini") is None, reason="gemini CLI not installed")
def test_gemini_extension_install_discovers_the_skill(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    # Listing is local, but the CLI refuses to start without an auth method.
    (home / ".gemini" / "settings.json").write_text(
        '{"security":{"auth":{"selectedType":"gemini-api-key"}}}', encoding="utf-8"
    )
    env = {
        "HOME": str(home),
        "GEMINI_API_KEY": "placeholder-not-a-key",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }

    install = _run(["gemini", "extensions", "install", str(pkg), "--consent"], env)
    assert install.returncode == 0, f"{install.stdout}\n{install.stderr}"
    skills = _run(["gemini", "skills", "list"], env)
    assert skills.returncode == 0, skills.stderr
    installed = home / ".gemini" / "extensions" / PLUGIN_NAME / "skills" / PLUGIN_NAME / "SKILL.md"
    listing = skills.stdout + skills.stderr  # the CLI prints the listing to stderr
    assert f"{PLUGIN_NAME} [Enabled]" in listing, listing
    assert installed.read_bytes() == CANONICAL_SKILL.read_bytes()
