from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from pygate.models import (
    ActionScope,
    AgentBrief,
    Confidence,
    Escalation,
    EscalationInfo,
    FailuresPayload,
    Finding,
    GateName,
    GateResult,
    GateStatus,
    InferredHint,
    PriorityAction,
    RepairAttempt,
    RepairReport,
    RetryPolicy,
    RunMode,
    RunStatus,
    Severity,
)


class TestFinding:
    def test_valid_finding(self):
        f = Finding(
            id="ruff_F401_foo_1",
            gate=GateName.LINT,
            severity=Severity.HIGH,
            summary="unused import",
            files=["foo.py"],
            rule="F401",
            line=1,
            actual=1,
            threshold=0,
        )
        assert f.id == "ruff_F401_foo_1"
        assert f.status == "fail"

    def test_finding_defaults(self):
        f = Finding(
            id="test",
            gate=GateName.TEST,
            severity=Severity.HIGH,
            summary="test failed",
            actual="failed",
            threshold="passed",
        )
        assert f.files == []
        assert f.rule is None
        assert f.raw == {}


class TestFailuresPayload:
    def test_valid_payload(self):
        p = FailuresPayload(
            run_id="run_123",
            mode=RunMode.CANARY,
            status=RunStatus.PASS,
            timestamp="2025-01-01T00:00:00Z",
            gates=[GateResult(name=GateName.LINT, status=GateStatus.PASS)],
            findings=[],
        )
        assert p.version == "1.0.0"
        assert p.changed_files == []

    def test_invalid_mode(self):
        with pytest.raises(ValidationError):
            FailuresPayload(
                run_id="run_123",
                mode=cast(RunMode, "invalid"),
                status=RunStatus.PASS,
                timestamp="2025-01-01T00:00:00Z",
                gates=[],
                findings=[],
            )


class TestAgentBrief:
    def test_valid_brief(self):
        b = AgentBrief(
            run_id="run_123",
            mode=RunMode.CANARY,
            status=RunStatus.FAIL,
            summary="1 finding",
            priority_actions=[
                PriorityAction(
                    finding_id="f1",
                    action="Fix it",
                    scope=ActionScope.SINGLE_FILE,
                    rationale="It's broken",
                )
            ],
            retry_policy=RetryPolicy(max_attempts=3, max_patch_lines=150, abort_on_no_improvement=2),
            escalation=EscalationInfo(required=True, reason_code="TEST"),
        )
        assert b.status == RunStatus.FAIL


class TestRepairModels:
    def test_repair_attempt(self):
        a = RepairAttempt(
            attempt=1,
            patch_lines=10,
            before_findings=3,
            after_findings=1,
            improved=True,
            worsened=False,
            status="fail",
        )
        assert a.improved is True

    def test_repair_report(self):
        r = RepairReport(status="pass", attempts=[])
        assert r.status == "pass"

    def test_escalation(self):
        e = Escalation(
            reason_code="NO_IMPROVEMENT",
            message="No improvement",
            evidence={"attempts": []},
        )
        assert e.status == "escalated"


class TestSerializationRoundtrip:
    def test_failures_roundtrip(self):
        p = FailuresPayload(
            run_id="run_123",
            mode=RunMode.FULL,
            status=RunStatus.FAIL,
            timestamp="2025-01-01T00:00:00Z",
            gates=[GateResult(name=GateName.LINT, status=GateStatus.FAIL, duration_ms=100)],
            findings=[
                Finding(
                    id="f1",
                    gate=GateName.LINT,
                    severity=Severity.HIGH,
                    summary="test",
                    actual=1,
                    threshold=0,
                )
            ],
            inferred_hints=[InferredHint(finding_id="f1", hint="check lint", confidence=Confidence.LOW)],
        )
        data = p.model_dump(mode="json")
        restored = FailuresPayload(**data)
        assert restored.run_id == p.run_id
        assert len(restored.findings) == 1
