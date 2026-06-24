"""Parametrized routing tests over a large synthetic case matrix."""

from __future__ import annotations

import pytest

from stepdiff.compaction.codec import choose_route
from stepdiff.compaction.diff_visual import VisualDiffResult
from stepdiff.schemas import BrowserAction, StepRecord, StepState
from routing_matrix_cases import ROUTING_CASES


def _build_step(case: dict, make_step_state) -> StepRecord:
    before = make_step_state(
        case["before_text"],
        case.get("before_nodes"),
    )
    after = make_step_state(
        case["after_text"],
        case.get("after_nodes"),
    )
    if case.get("visual_change"):
        before.screenshot_path = "screenshots/before.png"
        after.screenshot_path = "screenshots/after.png"

    return StepRecord(
        step_id="step_001",
        action=BrowserAction(
            type="click",
            selector="#btn",
            value=None,
            description=case.get("description", case["id"]),
        ),
        before=before,
        after=after,
        run_id="matrix",
    )


@pytest.mark.parametrize("case", ROUTING_CASES, ids=[c["id"] for c in ROUTING_CASES])
def test_routing_matrix_case(
    case: dict,
    make_step_state,
    tmp_run_folder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _build_step(case, make_step_state)

    if case.get("visual_change"):
        (tmp_run_folder / "screenshots" / "before.png").write_bytes(b"png")
        (tmp_run_folder / "screenshots" / "after.png").write_bytes(b"png")
        monkeypatch.setattr(
            "stepdiff.compaction.codec.compute_visual_diff",
            lambda *_a, **_k: VisualDiffResult(
                has_visual_change=True,
                change_fraction=0.1,
                summary="synthetic visual change",
            ),
        )

    route = choose_route(step, tmp_run_folder)

    assert route == case["expected_route"], (
        f"{case['id']}: expected {case['expected_route']!r}, got {route!r} "
        f"({case.get('description', '')})"
    )


def test_routing_matrix_has_many_cases() -> None:
    assert len(ROUTING_CASES) >= 25
