#!/usr/bin/env python3
"""
PyGate real-world evaluation suite.

Creates realistic Python project scenarios, runs pygate against each,
and reports results in a structured format.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PYGATE = "pygate"
RESULTS: list[dict[str, Any]] = []


def run(cmd: str, cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def setup_project(name: str, files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"pygate-eval-{name}-"))
    for path, content in files.items():
        p = d / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    run("git init -q && git add -A && git commit -m init --no-gpg-sign -q", str(d))
    return d


def run_scenario(
    name: str,
    files: dict[str, str],
    changed: list[str],
    mode: str = "canary",
    expect_run: str = "pass",
    expect_repair: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    d = setup_project(name, files)
    changed_file = d / "changed.txt"
    changed_file.write_text("\n".join(changed))

    # Run
    exit_code, stdout, stderr = run(f"{PYGATE} run --mode {mode} --changed-files changed.txt", str(d))
    try:
        run_result = json.loads(stdout)
    except json.JSONDecodeError:
        run_result = {"status": "error", "raw_stdout": stdout[:500], "raw_stderr": stderr[:500]}

    run_status = run_result.get("status", "error")

    # Read findings
    findings = []
    failures_path = d / ".pygate" / "failures.json"
    if failures_path.exists():
        fdata = json.loads(failures_path.read_text())
        findings = fdata.get("findings", [])

    # Summarize
    if failures_path.exists():
        run(f"{PYGATE} summarize --input .pygate/failures.json", str(d))

    # Repair (if there are failures)
    repair_result: dict[str, Any] | None = None
    if run_status == "fail" and expect_repair is not None:
        exit_code, stdout, stderr = run(
            f"{PYGATE} repair --input .pygate/failures.json --max-attempts 3",
            str(d),
            timeout=120,
        )
        try:
            repair_result = json.loads(stdout)
        except json.JSONDecodeError:
            repair_result = {"status": "error", "raw_stderr": stderr[:500]}

    # Check artifacts exist
    artifacts = {
        "failures.json": (d / ".pygate" / "failures.json").exists(),
        "run-metadata.json": (d / ".pygate" / "run-metadata.json").exists(),
        "agent-brief.json": (d / ".pygate" / "agent-brief.json").exists(),
        "agent-brief.md": (d / ".pygate" / "agent-brief.md").exists(),
    }

    result = {
        "scenario": name,
        "description": description,
        "run_status": run_status,
        "expected_run": expect_run,
        "run_correct": run_status == expect_run,
        "finding_count": len(findings),
        "finding_gates": list({f["gate"] for f in findings}),
        "finding_summaries": [f["summary"][:80] for f in findings],
        "repair_status": repair_result.get("status") if repair_result else None,
        "expected_repair": expect_repair,
        "repair_correct": (repair_result.get("status") == expect_repair) if expect_repair and repair_result else None,
        "artifacts": artifacts,
    }

    if repair_result and "attempts" in repair_result:
        result["repair_attempts"] = [
            {
                "attempt": a["attempt"],
                "before": a["before_findings"],
                "after": a["after_findings"],
                "improved": a["improved"],
            }
            for a in repair_result["attempts"]
        ]
    if repair_result and "reason_code" in repair_result:
        result["escalation_reason"] = repair_result["reason_code"]

    # Cleanup
    shutil.rmtree(d, ignore_errors=True)
    RESULTS.append(result)
    return result


# ============================================================
# SCENARIOS
# ============================================================


def scenario_1_clean_project():
    """Clean project, all gates should pass."""
    return run_scenario(
        "1-clean",
        {
            "src/app.py": 'def greet(name: str) -> str:\n    return f"Hello, {name}"\n',
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/app.py"],
        expect_run="pass",
        description="Clean project with no issues",
    )


def scenario_2_unused_imports():
    """Unused imports — fully auto-fixable by ruff."""
    return run_scenario(
        "2-unused-imports",
        {
            "src/app.py": (
                'import os\nimport sys\nimport json\n\ndef greet(name: str) -> str:\n    return f"Hello, {name}"\n'
            ),
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/app.py"],
        expect_run="fail",
        expect_repair="pass",
        description="3 unused imports, all auto-fixable",
    )


def scenario_3_mixed_fixable_unfixable():
    """Unused imports (fixable) + type errors (unfixable)."""
    return run_scenario(
        "3-mixed-lint-type",
        {
            "src/app.py": (
                "import os\nimport sys\n\n"
                "def add(a: int, b: str) -> int:\n    return a + b\n\n"
                "class Foo:\n    def bar(self) -> None:\n        return self.nonexistent()\n"
            ),
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/app.py"],
        expect_run="fail",
        expect_repair="escalated",
        description="2 unused imports (fixable) + 2 type errors (unfixable without model)",
    )


def scenario_4_formatting_only():
    """Badly formatted code — ruff format should fix it."""
    return run_scenario(
        "4-format-issues",
        {
            "src/app.py": ('import  os\nx=1\ny =   2\ndef   greet( name:str )->str:\n    return f"Hello, {name}"\n'),
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/app.py"],
        expect_run="fail",
        expect_repair="pass",  # ruff --fix removes unused import, ruff format fixes formatting
        description="Formatting issues + unused import",
    )


def scenario_5_failing_test():
    """Project with a failing test — full mode."""
    return run_scenario(
        "5-failing-test",
        {
            "src/__init__.py": "",
            "src/math.py": "def divide(a: int, b: int) -> float:\n    return a / b\n",
            "tests/__init__.py": "",
            "tests/test_math.py": (
                "from src.math import divide\n\n"
                "def test_divide():\n    assert divide(10, 2) == 5.0\n\n"
                "def test_divide_by_zero():\n    assert divide(10, 0) == 0\n"
            ),
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/math.py", "tests/test_math.py"],
        mode="full",
        expect_run="fail",
        expect_repair="escalated",
        description="One passing test + one failing test (division by zero)",
    )


def scenario_6_multi_file_lint():
    """Lint issues spread across multiple files."""
    return run_scenario(
        "6-multi-file-lint",
        {
            "src/models.py": "import os\nimport typing\n\nclass User:\n    name: str\n    age: int\n",
            "src/views.py": "import sys\nimport json\n\ndef index() -> str:\n    return 'hello'\n",
            "src/utils.py": "import collections\n\ndef noop() -> None:\n    pass\n",
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/models.py", "src/views.py", "src/utils.py"],
        expect_run="fail",
        expect_repair="pass",
        description="Unused imports across 3 files, all auto-fixable",
    )


def scenario_7_star_import():
    """Star import — ruff flags but can't safely auto-fix."""
    return run_scenario(
        "7-star-import",
        {
            "src/app.py": "from os.path import *\n\ndef get_home() -> str:\n    return expanduser('~')\n",
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/app.py"],
        expect_run="fail",
        expect_repair="escalated",
        description="Star import — flagged but not auto-fixable",
    )


def scenario_8_large_file_many_issues():
    """File with many different kinds of issues."""
    code = (
        "import os\nimport sys\nimport json\nimport re\nimport collections\n\n"
        "x = 1\ny = 2\nz = 3\n\n"
        "def process(data: str) -> int:\n"
        "    result = json.loads(data)\n"
        "    return result\n\n"  # type error: returns dict, annotated int
        "def bad_compare(a: int, b: str) -> bool:\n"
        "    return a == b\n\n"
        "class Service:\n"
        "    def __init__(self):\n"
        "        self.data = []\n\n"
        "    def run(self) -> None:\n"
        "        import os\n"  # reimport
        "        os.getcwd()\n"
    )
    return run_scenario(
        "8-large-mixed",
        {
            "src/service.py": code,
            "pyproject.toml": '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        },
        changed=["src/service.py"],
        expect_run="fail",
        expect_repair="pass",  # ruff --fix handles all lint issues; pyright basic mode doesn't flag the type issues
        description="Many issues: unused imports, reimport, type mismatches",
    )


# ============================================================
# RUNNER
# ============================================================


def main():
    scenarios = [
        scenario_1_clean_project,
        scenario_2_unused_imports,
        scenario_3_mixed_fixable_unfixable,
        scenario_4_formatting_only,
        scenario_5_failing_test,
        scenario_6_multi_file_lint,
        scenario_7_star_import,
        scenario_8_large_file_many_issues,
    ]

    print("=" * 70)
    print("PyGate Evaluation Suite")
    print("=" * 70)

    for fn in scenarios:
        name = fn.__name__.replace("scenario_", "")
        print(f"\n--- {name} ---")
        try:
            result = fn()
            run_ok = "PASS" if result["run_correct"] else "FAIL"
            print(f"  Run:    {result['run_status']:10s}  (expected {result['expected_run']}) [{run_ok}]")
            print(f"  Found:  {result['finding_count']} findings {result['finding_gates']}")

            if result["repair_status"]:
                rep_ok = "PASS" if result["repair_correct"] else "FAIL"
                print(f"  Repair: {result['repair_status']:10s}  (expected {result['expected_repair']}) [{rep_ok}]")
                if "repair_attempts" in result:
                    for a in result["repair_attempts"]:
                        arrow = "improved" if a["improved"] else "no change"
                        print(f"    attempt {a['attempt']}: {a['before']}→{a['after']} ({arrow})")
                if "escalation_reason" in result:
                    print(f"    reason: {result['escalation_reason']}")

            missing = [k for k, v in result["artifacts"].items() if not v]
            if missing:
                print(f"  Artifacts missing: {missing}")

        except Exception as e:
            print(f"  ERROR: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total = len(RESULTS)
    run_correct = sum(1 for r in RESULTS if r["run_correct"])
    repair_tested = [r for r in RESULTS if r["expected_repair"] is not None]
    repair_correct = sum(1 for r in repair_tested if r["repair_correct"])

    print(f"  Run detection:  {run_correct}/{total} correct")
    print(f"  Repair outcome: {repair_correct}/{len(repair_tested)} correct")

    all_artifacts = all(all(r["artifacts"].values()) for r in RESULTS if r["run_status"] != "pass")
    print(f"  All artifacts:  {'YES' if all_artifacts else 'NO'}")

    # Write results JSON
    out = Path(__file__).parent / "eval_results.json"
    out.write_text(json.dumps(RESULTS, indent=2))
    print(f"\n  Full results: {out}")


if __name__ == "__main__":
    main()
