from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class RunMode(str, Enum):
    CANARY = "canary"
    FULL = "full"


class RunStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GateName(str, Enum):
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"


class ActionScope(str, Enum):
    SINGLE_FILE = "single_file"
    MULTI_FILE = "multi_file"
    CROSS_MODULE = "cross_module"


# --- Gate execution models ---


class GateResult(BaseModel):
    name: GateName
    status: GateStatus
    duration_ms: int = 0


class Finding(BaseModel):
    id: str
    gate: GateName
    severity: Severity
    summary: str
    files: list[str] = Field(default_factory=list)
    rule: str | None = None
    line: int | None = None
    column: int | None = None
    actual: int | str
    threshold: int | str
    status: str = "fail"
    raw: dict[str, Any] = Field(default_factory=dict)


class InferredHint(BaseModel):
    finding_id: str
    hint: str
    confidence: Confidence


# --- Artifact payloads ---


class FailuresPayload(BaseModel):
    version: str = "1.0.0"
    run_id: str
    mode: RunMode
    status: RunStatus
    timestamp: str
    repo: str | None = None
    branch: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    gates: list[GateResult]
    findings: list[Finding]
    inferred_hints: list[InferredHint] = Field(default_factory=list)


class CommandTrace(BaseModel):
    command: str
    cwd: str
    started_at: str
    duration_ms: int
    exit_code: int | None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    argv: list[str] = Field(default_factory=list)
    shell: bool = False
    timeout_seconds: float | None = None
    output_truncated: bool = False
    signal: int | None = None
    missing_executable: bool = False
    error: str | None = None
    diagnostics: list[str] = Field(default_factory=list)


class EnvironmentInfo(BaseModel):
    python_version: str
    platform: str
    virtualenv: str | None = None
    resolver: str | None = None
    installed_packages: dict[str, str] = Field(default_factory=dict)


class RunMetadata(BaseModel):
    run_id: str
    mode: RunMode
    started_at: str
    completed_at: str
    duration_ms: int
    config_source: str
    environment: EnvironmentInfo
    command_traces: list[CommandTrace]


# --- Agent brief models ---


class PriorityAction(BaseModel):
    finding_id: str
    action: str
    scope: ActionScope
    target_files: list[str] = Field(default_factory=list)
    rationale: str


class RetryPolicy(BaseModel):
    max_attempts: int
    max_patch_lines: int
    abort_on_no_improvement: int


class EscalationInfo(BaseModel):
    required: bool
    reason_code: str | None = None
    message: str | None = None


class AgentBrief(BaseModel):
    run_id: str
    mode: RunMode
    status: RunStatus
    summary: str
    priority_actions: list[PriorityAction]
    retry_policy: RetryPolicy
    escalation: EscalationInfo | None = None


# --- Repair models ---


class RepairAttempt(BaseModel):
    attempt: int
    patch_lines: int
    before_findings: int
    after_findings: int
    improved: bool
    worsened: bool
    status: str
    actions: list[dict[str, Any]] = Field(default_factory=list)


class RepairReport(BaseModel):
    status: str
    attempts: list[RepairAttempt] = Field(default_factory=list)


class Escalation(BaseModel):
    status: str = "escalated"
    reason_code: str
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
