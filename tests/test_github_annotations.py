from __future__ import annotations

import json
from pathlib import Path

from pygate.github_annotations import render_annotations


def test_annotations_render_one_safe_location_and_skip_unsupported_findings(tmp_path: Path) -> None:
    failures = tmp_path / "failures.json"
    failures.write_text(json.dumps({"findings": [
        {"files": ["src/a,b:c.py"], "line": 7, "column": 2, "summary": "secret\ncommand"},
        {"files": ["/etc/passwd"], "line": 1},
        {"files": ["tests/test_x.py"]},
        {"files": ["a.py", "b.py"], "line": 1},
        {"files": ["bool.py"], "line": True},
        {"files": ["zero.py"], "line": 0},
        {"files": ["column.py"], "line": 1, "column": True},
    ]}), encoding="utf-8")
    assert render_annotations(failures) == [
        "::error file=src/a%2Cb%3Ac.py,line=7,col=2::PyGate reported a diagnostic.",
        "::error file=column.py,line=1::PyGate reported a diagnostic.",
    ]


def test_annotations_are_capped(tmp_path: Path) -> None:
    failures = tmp_path / "failures.json"
    failures.write_text(json.dumps({"findings": [
        {"files": [f"src/{index}.py"], "line": 1} for index in range(101)
    ]}), encoding="utf-8")
    annotations = render_annotations(failures)
    assert len(annotations) == 100
    assert annotations[-1].startswith("::error file=src/99.py,line=1")
