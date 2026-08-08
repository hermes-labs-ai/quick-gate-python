from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pygate import __version__
from pygate.api import evaluate
from pygate.env import check_environment
from pygate.fs import load_changed_files
from pygate.models import RunMode
from pygate.repair_command import execute_repair
from pygate.run_command import execute_run
from pygate.summarize_command import execute_summarize


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pygate",
        description="Deterministic quality gate CLI for Python projects",
    )
    parser.add_argument("--version", action="version", version=f"pygate {__version__}")

    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Run quality gates")
    run_p.add_argument("--mode", required=True, choices=["canary", "full"], help="Gate mode")
    run_p.add_argument(
        "--changed-files",
        default=None,
        help="Optional path to a newline-delimited or JSON changed-files list",
    )
    run_p.add_argument(
        "--output-dir",
        default=None,
        help="Write artifacts to this directory; omitted for side-effect-free JSON output",
    )
    run_p.add_argument(
        "--unsafe-shell",
        action="store_true",
        help="Explicitly enable shell parsing for legacy command strings",
    )

    # summarize
    sum_p = sub.add_parser("summarize", help="Generate agent brief from failures")
    sum_p.add_argument("--input", required=True, help="Path to failures.json")

    # repair
    rep_p = sub.add_parser("repair", help="Run bounded repair loop")
    rep_p.add_argument("--input", required=True, help="Path to failures.json")
    rep_p.add_argument("--max-attempts", type=int, default=None, help="Maximum repair attempts")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Print environment warnings
    warnings = check_environment(command=args.command)
    for w in warnings:
        print(f"[pygate warn] {w}", file=sys.stderr)

    cwd = Path.cwd()

    if args.command == "run":
        changed_files: list[str] = []
        if args.changed_files:
            changed_files_path = Path(args.changed_files)
            if not changed_files_path.is_absolute():
                changed_files_path = cwd / changed_files_path
            changed_files = load_changed_files(changed_files_path)

        mode = RunMode(args.mode)
        if args.output_dir:
            result = execute_run(
                mode=mode,
                changed_files=changed_files,
                cwd=cwd,
                output_dir=Path(args.output_dir),
                unsafe_shell=args.unsafe_shell,
            )
            status = result["status"]
        else:
            result_model = evaluate(
                mode=mode,
                checked_paths=changed_files,
                cwd=cwd,
                unsafe_shell=args.unsafe_shell,
            )
            result = result_model.model_dump(mode="json", by_alias=True)
            status = result["status"]
        print(json.dumps(result, indent=2))
        sys.exit(0 if status == "pass" else 1)

    elif args.command == "summarize":
        input_path = args.input
        if not Path(input_path).is_absolute():
            input_path = str(cwd / input_path)
        result = execute_summarize(input_path=input_path, cwd=cwd)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    elif args.command == "repair":
        input_path = args.input
        if not Path(input_path).is_absolute():
            input_path = str(cwd / input_path)
        result = execute_repair(
            input_path=input_path,
            max_attempts=args.max_attempts,
            cwd=cwd,
        )
        print(json.dumps(result, indent=2))
        status = result.get("status", "")
        if status == "pass":
            sys.exit(0)
        else:
            # execute_repair returns "pass" or "escalated"
            sys.exit(2)
