"""Compaction routes — text_only vs crop_with_context."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from stepdiff.compaction.diff_dom import diff_dom
from stepdiff.compaction.diff_visual import (
    SCREENSHOT_BASELINE_TOKENS,
    diff_screenshots,
    estimate_tokens,
)
from stepdiff.compaction.types import VisualDiff
from stepdiff.schemas import CompactObservation, StepState

CompactionRoute = Literal["text_only", "crop_with_context"]


def _savings_pct(compact_tokens: int, baseline_tokens: int) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return round((1.0 - compact_tokens / baseline_tokens) * 100.0, 2)


def _build_text_content(dom_summary: str, added: list[str], removed: list[str]) -> str:
    lines = [f"DOM changes: {dom_summary}"]
    if added:
        lines.append("Added: " + "; ".join(added[:10]))
    if removed:
        lines.append("Removed: " + "; ".join(removed[:10]))
    return "\n".join(lines)


def compact_step(
    step_id: str,
    before: StepState,
    after: StepState,
    route: CompactionRoute,
    *,
    run_dir: Path | None = None,
) -> CompactObservation:
    dom_diff = diff_dom(before, after)
    baseline_tokens = SCREENSHOT_BASELINE_TOKENS
    crop_path: str | None = None
    visual_diff: VisualDiff | None = None

    if route == "text_only":
        content = _build_text_content(
            dom_diff.summary,
            dom_diff.added_nodes,
            dom_diff.removed_nodes,
        )
        token_estimate = estimate_tokens(content)
        confidence = 0.85 if dom_diff.summary != "no DOM changes detected" else 0.5
    else:
        diff_path = None
        if run_dir:
            diff_path = run_dir / "screenshots" / f"{step_id}_diff.png"
        visual_diff = diff_screenshots(
            before,
            after,
            run_dir=run_dir,
            diff_output_path=diff_path,
            run_ocr=True,
        )
        parts = [f"DOM: {dom_diff.summary}"]
        if visual_diff.ocr_text:
            parts.append(f"OCR: {visual_diff.ocr_text}")
        if visual_diff.bounding_box:
            bb = visual_diff.bounding_box
            parts.append(f"Changed region: ({bb.x},{bb.y}) {bb.width}x{bb.height}")
        content = "\n".join(parts)
        crop_path = visual_diff.diff_image_path
        token_estimate = estimate_tokens(content) + (200 if crop_path else 0)
        confidence = min(1.0, 0.6 + visual_diff.change_ratio * 2)

    return CompactObservation(
        step_id=step_id,
        route=route,
        content=content,
        crop_path=crop_path,
        token_estimate=token_estimate,
        baseline_token_estimate=baseline_tokens,
        confidence=round(confidence, 3),
        savings_pct=_savings_pct(token_estimate, baseline_tokens),
    )
