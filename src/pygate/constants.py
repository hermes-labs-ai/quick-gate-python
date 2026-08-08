from __future__ import annotations

PYGATE_DIR = ".pygate"
FAILURES_FILE = ".pygate/failures.json"
RUN_METADATA_FILE = ".pygate/run-metadata.json"
AGENT_BRIEF_JSON_FILE = ".pygate/agent-brief.json"
AGENT_BRIEF_MD_FILE = ".pygate/agent-brief.md"
REPAIR_REPORT_FILE = ".pygate/repair-report.json"
ESCALATION_FILE = ".pygate/escalation.json"
PYTEST_REPORT_FILE = ".pygate/pytest-report.json"
GATE_RESULT_FILE = "gate-result.json"

DEFAULT_POLICY: dict[str, int] = {
    "max_attempts": 3,
    "max_patch_lines": 150,
    "abort_on_no_improvement": 2,
    "time_cap_seconds": 1200,
    "command_timeout_seconds": 120,
    "gate_timeout_seconds": 600,
    "output_cap_bytes": 1_048_576,
}

CONTRACT_VERSION = "gate-result/v1"
CONFIG_VERSION = "pygate-config/v1"


class EscalationCode:
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    PATCH_BUDGET_EXCEEDED = "PATCH_BUDGET_EXCEEDED"
    UNKNOWN_BLOCKER = "UNKNOWN_BLOCKER"
    UNRESOLVED_DETERMINISTIC_FAILURES = "UNRESOLVED_DETERMINISTIC_FAILURES"
    # Reserved for future use (v2 model-assisted repair)
    ARCHITECTURAL_CHANGE_REQUIRED = "ARCHITECTURAL_CHANGE_REQUIRED"
    FLAKY_EVALUATOR = "FLAKY_EVALUATOR"
    ENVIRONMENT_DRIFT = "ENVIRONMENT_DRIFT"
    TEST_FIXTURE_OR_EXTERNAL_DEP = "TEST_FIXTURE_OR_EXTERNAL_DEP"
