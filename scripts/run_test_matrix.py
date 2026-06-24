#!/usr/bin/env python3
"""Run the full StepDiff test matrix and print a summary."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

MATRIX_TESTS = [
    "tests/test_routing_matrix.py",
    "tests/test_dom_diff_matrix.py",
    "tests/test_example_runs.py",
    "tests/test_codec_routing.py",
    "tests/test_diff_dom.py",
    "tests/test_tasks.py",
]


def _count_cases() -> dict[str, int]:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    from dom_diff_matrix_cases import DOM_DIFF_CASES
    from routing_matrix_cases import ROUTING_CASES

    examples = list((PROJECT_ROOT / "examples" / "runs").glob("*/steps.jsonl"))
    tasks = list((PROJECT_ROOT / "tasks").glob("*.json"))

    return {
        "routing_matrix": len(ROUTING_CASES),
        "dom_diff_matrix": len(DOM_DIFF_CASES),
        "example_fixtures": len(examples),
        "playwright_tasks": len(tasks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run StepDiff synthetic test matrix")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run entire tests/ suite instead of matrix subset only",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Quiet pytest output",
    )
    args = parser.parse_args()

    counts = _count_cases()
    synthetic = counts["routing_matrix"] + counts["dom_diff_matrix"]
    print("StepDiff test matrix")
    print(f"  routing cases:  {counts['routing_matrix']}")
    print(f"  dom diff cases: {counts['dom_diff_matrix']}")
    print(f"  example runs:   {counts['example_fixtures']}")
    print(f"  task files:     {counts['playwright_tasks']}")
    print(f"  synthetic total: {synthetic} (+ example contracts + unit tests)\n")

    targets = ["tests"] if args.full else MATRIX_TESTS
    cmd = [sys.executable, "-m", "pytest", *targets]
    if args.quiet:
        cmd.append("-q")
    else:
        cmd.extend(["-v", "--tb=short"])

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
