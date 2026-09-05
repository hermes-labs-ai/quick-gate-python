from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every place that tells a consumer how to reference the root action.
DOCUMENTED_PIN_SOURCES = (
    "README.md",
    "SECURITY.md",
    "llms.txt",
    ".github/workflows/example-usage.yml",
)

SELF_REFERENCE = re.compile(r"hermes-labs-ai/quick-gate-python@(\S+?)(?=[`\s]|$)")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _documented_refs() -> dict[str, list[str]]:
    return {source: SELF_REFERENCE.findall((REPO_ROOT / source).read_text()) for source in DOCUMENTED_PIN_SOURCES}


def test_every_documented_source_pins_the_root_action() -> None:
    for source, refs in _documented_refs().items():
        assert refs, f"{source} documents no root-action reference"


def test_documented_pins_are_immutable_commits() -> None:
    for source, refs in _documented_refs().items():
        for ref in refs:
            assert COMMIT_SHA.match(ref), (
                f"{source} references the root action at {ref!r}. The pinning policy requires a "
                "40-character commit SHA: release tags predate the root action.yml and mutable "
                "branch references are not allowed."
            )


def test_documented_pins_agree() -> None:
    refs = _documented_refs()
    distinct = {ref for source_refs in refs.values() for ref in source_refs}
    assert len(distinct) == 1, "Documented root-action pins disagree, so at least one source is stale: " + "; ".join(
        f"{source}={sorted(set(source_refs))}" for source, source_refs in refs.items()
    )
