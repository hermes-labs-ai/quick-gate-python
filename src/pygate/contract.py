from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from pygate.constants import CONTRACT_VERSION


class CheckResult(BaseModel):
    name: str
    status: Literal["pass", "fail", "timeout", "missing", "error", "skipped"]
    argv: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0
    exit_code: int | None = None
    signal: int | None = None
    timed_out: bool = False
    output_truncated: bool = False
    stdout: str = ""
    stderr: str = ""
    diagnostics: list[str] = Field(default_factory=list)


class GateResultV1(BaseModel):
    contract_schema: Literal["gate-result/v1"] = Field(default=CONTRACT_VERSION, alias="schema")
    status: Literal["pass", "fail", "timeout", "error"]
    snapshot_digest: str
    checked_paths: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    command_versions: dict[str, str | dict[str, Any]] = Field(default_factory=dict)
    elapsed_ms: int = 0
    output_truncated: bool = False
    errors: list[str | dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[str | dict[str, Any]] = Field(default_factory=list)
    config_identity: str = "defaults"
    config_digest: str = ""
    config_version: str = "pygate-config/v1"
    package_version: str = ""
    snapshot_digest_after: str | None = None
    snapshot_changed: bool = False

    @property
    def schema(self) -> str:
        return self.contract_schema


def serialize_gate_result(result: GateResultV1) -> str:
    """Return deterministic JSON suitable for hashing, fixtures, and transport."""

    return json.dumps(
        result.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
