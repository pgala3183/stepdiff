#!/usr/bin/env python3
"""Compact a saved StepDiff run folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from stepdiff.compaction.codec import choose_route, compact_step
from stepdiff.compaction.routes import CompactionRoute
from stepdiff.schemas import CompactObservation, StepRecord
from stepdiff.storage import load_steps, save_compact_observation

PROJECT_ROOT = Path(__file__).parent.parent


def _project_root() -> Path:
    return PROJECT_ROOT


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


def _step_number(step_id: str, index: int) -> int:
    if step_id.startswith("step_") and step_id[5:].isdigit():
        return int(step_id[5:])
    return index + 1


def _screenshot_path(run_folder: Path, screenshot_rel: str | None) -> Path | None:
    if not screenshot_rel:
        return None
    return run_folder / screenshot_rel


def _check_screenshots(step: StepRecord, run_folder: Path) -> list[str]:
    warnings: list[str] = []
    for phase, state in (("before", step.before), ("after", step.after)):
        rel = state.screenshot_path
        if not rel:
            warnings.append(f"{step.step_id}: missing {phase} screenshot path")
            continue
        path = _screenshot_path(run_folder, rel)
        if path is None or not path.exists():
            warnings.append(f"{step.step_id}: {phase} screenshot not found at {rel}")
    return warnings


def _savings_fraction(obs: CompactObservation) -> float:
    if obs.baseline_token_estimate <= 0:
        return 0.0
    return 1.0 - (obs.token_estimate / obs.baseline_token_estimate)


def compact_run_folder(
    run_folder_arg: str,
    *,
    as_json: bool = False,
) -> list[CompactObservation]:
    run_folder, run_id = resolve_run_folder(run_folder_arg)
    steps = load_steps(run_id)

    if not steps:
        print(f"warning: no steps found in {run_folder / 'steps.jsonl'}", file=sys.stderr)
        return []

    observations: list[CompactObservation] = []
    total_compact = 0
    total_baseline = 0

    for index, step in enumerate(steps):
        for warning in _check_screenshots(step, run_folder):
            print(f"warning: {warning}", file=sys.stderr)

        route = choose_route(step, run_folder)
        obs = compact_step(
            step.step_id,
            step.before,
            step.after,
            route,
            run_dir=run_folder,
        )
        observations.append(obs)
        save_compact_observation(run_id, obs)

        total_compact += obs.token_estimate
        total_baseline += obs.baseline_token_estimate

        if not as_json:
            step_num = _step_number(step.step_id, index)
            savings = _savings_fraction(obs)
            preview = obs.content[:60].replace("\n", " ")
            print(
                f"step {step_num}: {obs.route}, {savings:.2%} saved, "
                f"confidence {obs.confidence:.2f} - {preview}"
            )

    if total_baseline > 0:
        total_pct = 1.0 - (total_compact / total_baseline)
    else:
        total_pct = 0.0

    if as_json:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "run_folder": str(run_folder),
            "steps": [obs.model_dump(mode="json") for obs in observations],
            "total_steps": len(observations),
            "total_compact_tokens": total_compact,
            "total_baseline_tokens": total_baseline,
            "overall_savings_pct": round(total_pct * 100, 2),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"total: {len(observations)} step(s), {total_compact} compact tokens "
            f"vs {total_baseline} baseline, {total_pct:.2%} saved"
        )

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact a saved StepDiff run folder")
    parser.add_argument(
        "run_folder",
        help="Path to the run folder (e.g. runs/local_checkout_abc123)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    args = parser.parse_args()

    try:
        observations = compact_run_folder(args.run_folder, as_json=args.json)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not observations:
        sys.exit(0)


if __name__ == "__main__":
    main()
