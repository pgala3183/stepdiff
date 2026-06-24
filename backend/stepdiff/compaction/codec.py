"""Main compaction router — orchestrates per-step compaction."""

from __future__ import annotations

from pathlib import Path

from stepdiff.compaction.diff_visual import compute_visual_diff
from stepdiff.compaction.diff_dom import diff_dom_text, dom_prefers_text_route
from stepdiff.compaction.routes import CompactionRoute, compact_step
from stepdiff.schemas import CompactObservation, StepRecord
from stepdiff.storage import load_steps, run_folder_path, save_compact_observation

__all__ = ["choose_route", "compact_run", "compact_run_id", "compact_step", "CompactionRoute"]


def choose_route(step: StepRecord, run_folder: Path) -> CompactionRoute:
    text_diff = diff_dom_text(step.before, step.after)
    if text_diff.error_messages:
        return "text_only"

    visual_change = False
    before_rel = step.before.screenshot_path
    after_rel = step.after.screenshot_path
    if before_rel and after_rel:
        before_path = run_folder / before_rel
        after_path = run_folder / after_rel
        if before_path.exists() and after_path.exists():
            visual = compute_visual_diff(str(before_path), str(after_path), run_folder)
            visual_change = visual.has_visual_change

    if visual_change and not dom_prefers_text_route(text_diff):
        return "crop_with_context"
    return "text_only"


def compact_run(
    steps: list[StepRecord],
    *,
    route: CompactionRoute = "text_only",
    run_dir: Path | None = None,
) -> list[CompactObservation]:
    observations: list[CompactObservation] = []
    for step in steps:
        observations.append(
            compact_step(
                step.step_id,
                step.before,
                step.after,
                route,
                run_dir=run_dir,
            )
        )
    return observations


def compact_run_id(run_id: str) -> list[CompactObservation]:
    """Compact all steps for a run using auto-selected routes per step."""
    steps = load_steps(run_id)
    run_folder = run_folder_path(run_id)
    observations: list[CompactObservation] = []
    for step in steps:
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
    return observations
