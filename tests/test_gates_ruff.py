from __future__ import annotations

import json
from pathlib import Path

from pygate.gates.ruff import parse_ruff_output, resolve_ruff_command
from pygate.models import GateName, Severity


class TestResolveRuffCommand:
    def test_default(self):
        assert resolve_ruff_command({}) == "ruff check --no-cache --output-format json --exclude .pygate ."

    def test_custom(self):
        assert resolve_ruff_command({"lint": "ruff check src/"}) == "ruff check src/"


class TestParseRuffOutput:
    def test_parse_fixture(self, ruff_output: list):
        stdout = json.dumps(ruff_output)
        cwd = Path("/tmp/project")
        findings = parse_ruff_output(stdout, "", 1, cwd)

        assert len(findings) == 3

        f401 = findings[0]
        assert f401.gate == GateName.LINT
        assert f401.rule == "F401"
        assert f401.severity == Severity.HIGH
        assert f401.files == ["src/foo.py"]
        assert f401.line == 1
        assert "unused" in f401.summary.lower()

        e501 = findings[1]
        assert e501.rule == "E501"
        assert e501.severity == Severity.HIGH

        w291 = findings[2]
        assert w291.rule == "W291"
        assert w291.severity == Severity.MEDIUM
        assert w291.files == ["src/bar.py"]

    def test_empty_output(self):
        findings = parse_ruff_output("", "", 0, Path("/tmp"))
        assert findings == []

    def test_invalid_json(self):
        findings = parse_ruff_output("not json", "", 1, Path("/tmp"))
        assert findings == []

    def test_non_array_json(self):
        findings = parse_ruff_output('{"error": true}', "", 1, Path("/tmp"))
        assert findings == []

    def test_fix_applicability_in_raw(self, ruff_output: list):
        stdout = json.dumps(ruff_output)
        findings = parse_ruff_output(stdout, "", 1, Path("/tmp/project"))
        assert findings[0].raw["fix_applicability"] == "safe"
