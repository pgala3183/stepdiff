#!/usr/bin/env python3
"""Evaluate a compacted run."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from stepdiff.compaction.codec import compact_run
from stepdiff.compaction.routes import CompactionRoute
from stepdiff.eval.evaluator import compare_runs, evaluate_run
from stepdiff.storage import (
    get_run_folder,
    list_runs,
    load_compact_observations,
    load_steps,
    save_compact_observation,
)

PROJECT_ROOT = Path(__file__).parent.parent


def resolve_run_folder(run_folder_arg: str) -> tuple[Path, str]:
    run_folder = Path(run_folder_arg)
    if not run_folder.is_absolute():
        run_folder = PROJECT_ROOT / run_folder
    run_folder = run_folder.resolve()
    if not run_folder.exists():
        raise FileNotFoundError(
            f"Run folder not found: {run_folder}\n"
            f"Expected a path like 'runs/<run_id>' under {PROJECT_ROOT}"
        )
    return run_folder, run_folder.name


def ensure_compacted(run_id: str, route: CompactionRoute) -> None:
    observations = load_compact_observations(run_id)
    if observations:
        return
    steps = load_steps(run_id)
    run_dir = get_run_folder(run_id)
    observations = compact_run(steps, route=route, run_dir=run_dir)
    for obs in observations:
        save_compact_observation(run_id, obs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a StepDiff run")
    parser.add_argument(
        "run_folder",
        help="Path to the run folder (e.g. runs/local_checkout_abc123)",
    )
    parser.add_argument(
        "--predictor",
        choices=["heuristic", "llm"],
        default="heuristic",
        help="heuristic: fast smoke test; llm: Claude compact predictor",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run compact vs full-state baseline comparison",
    )
    parser.add_argument(
        "--route",
        choices=["text_only", "crop_with_context"],
        default="text_only",
        help="Compaction route if not already compacted",
    )
    args = parser.parse_args()

    try:
        _, run_id = resolve_run_folder(args.run_folder)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if run_id not in list_runs():
        print(f"error: run '{run_id}' not found under runs/", file=sys.stderr)
        sys.exit(1)

    route: CompactionRoute = args.route
    ensure_compacted(run_id, route)

    steps = load_steps(run_id)
    if len(steps) < 2:
        print(
            f"error: run '{run_id}' has {len(steps)} step(s); replay eval needs at least 2 "
            "(predict the next action after each step).\n"
            "Try a multi-step task, e.g. tasks/modal_flow.json or tasks/local_checkout.json.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.compare:
        comparison = compare_runs(run_id)
        print(json.dumps(asdict(comparison), indent=2))
        parity_score = comparison.compact_parity
    else:
        report = evaluate_run(run_id, predictor=args.predictor)
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        parity_score = report.parity_score

    sys.exit(0 if parity_score >= 0.8 else 1)


if __name__ == "__main__":
    main()
