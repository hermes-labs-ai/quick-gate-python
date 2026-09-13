from __future__ import annotations

import json
from pathlib import Path

from pygate.github_summary import render_summary


def test_summary_counts_known_checks_without_rendering_untrusted_artifact_content(tmp_path: Path) -> None:
    failures = tmp_path / "failures.json"
    failures.write_text(
        json.dumps(
            {
                "gates": [
                    {"name": "lint", "status": "pass"},
                    {"name": "typecheck", "status": "pass"},
                    {"name": "test", "status": "fail"},
                    {
                        "name": "[unsafe](https://example.invalid)",
                        "status": "pass",
                        "summary": "`raw argv` /absolute/path secret error",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = render_summary(status="pass", repair_status="skipped", failures_path=failures)

    assert "Status: pass" in summary
    assert "Checks: pass: 2, fail: 1, skipped: 0 (total: 3)" in summary
    assert "Repair: skipped" in summary
    assert "Version: 0.3.1" in summary
    assert "Source: [PyGate action source](https://github.com/hermes-labs-ai/quick-gate-python)" in summary
    assert "unsafe" not in summary
    assert "raw argv" not in summary
    assert "/absolute/path" not in summary


def test_summary_marks_unreadable_artifact_and_unknown_states_unavailable(tmp_path: Path) -> None:
    summary = render_summary(
        status="<script>",
        repair_status="unknown",
        failures_path=tmp_path / "missing.json",
    )

    assert "Status: unavailable" in summary
    assert "Checks: unavailable" in summary
    assert "Repair: unavailable" in summary
