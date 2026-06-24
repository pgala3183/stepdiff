"""Tests for compaction route selection."""

from __future__ import annotations

from stepdiff.compaction.codec import choose_route
from stepdiff.compaction.diff_visual import VisualDiffResult


def test_dom_text_only_change_routes_to_text_only(
    make_step_record, tmp_run_folder
) -> None:
    step = make_step_record("Hello", "Hello\nWorld")

    route = choose_route(step, tmp_run_folder)

    assert route == "text_only"


def test_visual_only_change_routes_to_crop_with_context(
    make_step_state, make_step_record, tmp_run_folder, monkeypatch
) -> None:
    before = make_step_state("Same text")
    after = make_step_state("Same text")
    before.screenshot_path = "screenshots/before.png"
    after.screenshot_path = "screenshots/after.png"
    (tmp_run_folder / "screenshots" / "before.png").write_bytes(b"png")
    (tmp_run_folder / "screenshots" / "after.png").write_bytes(b"png")

    from stepdiff.schemas import BrowserAction, StepRecord

    step = StepRecord(
        step_id="step_001",
        action=BrowserAction(
            type="click",
            selector="#btn",
            value=None,
            description="click",
        ),
        before=before,
        after=after,
        run_id="test_run",
    )

    monkeypatch.setattr(
        "stepdiff.compaction.codec.compute_visual_diff",
        lambda *_args, **_kwargs: VisualDiffResult(
            has_visual_change=True,
            change_fraction=0.25,
            summary="large visual change",
        ),
    )

    route = choose_route(step, tmp_run_folder)

    assert route == "crop_with_context"


def test_error_message_routes_to_text_only_despite_visual_change(
    make_step_state, tmp_run_folder, monkeypatch
) -> None:
    before = make_step_state("Email\nPassword")
    after = make_step_state("Email\nEmail is required\nPassword")
    before.screenshot_path = "screenshots/before.png"
    after.screenshot_path = "screenshots/after.png"
    (tmp_run_folder / "screenshots" / "before.png").write_bytes(b"png")
    (tmp_run_folder / "screenshots" / "after.png").write_bytes(b"png")

    from stepdiff.schemas import BrowserAction, StepRecord

    step = StepRecord(
        step_id="step_001",
        action=BrowserAction(
            type="click",
            selector="#submit",
            value=None,
            description="submit",
        ),
        before=before,
        after=after,
        run_id="test_run",
    )

    monkeypatch.setattr(
        "stepdiff.compaction.codec.compute_visual_diff",
        lambda *_args, **_kwargs: VisualDiffResult(
            has_visual_change=True,
            change_fraction=0.5,
            summary="visual change",
        ),
    )

    route = choose_route(step, tmp_run_folder)

    assert route == "text_only"


def test_visual_with_value_only_field_change_routes_to_crop(
    make_step_state, tmp_run_folder, monkeypatch
) -> None:
    before = make_step_state('- spinbutton "Quantity": "1"')
    after = make_step_state('- spinbutton "Quantity": "5"')
    before.screenshot_path = "screenshots/before.png"
    after.screenshot_path = "screenshots/after.png"
    (tmp_run_folder / "screenshots" / "before.png").write_bytes(b"png")
    (tmp_run_folder / "screenshots" / "after.png").write_bytes(b"png")

    from stepdiff.schemas import BrowserAction, StepRecord

    step = StepRecord(
        step_id="step_003",
        action=BrowserAction(
            type="type",
            selector="#quantity",
            value="5",
            description="update chart",
        ),
        before=before,
        after=after,
        run_id="test_run",
    )

    monkeypatch.setattr(
        "stepdiff.compaction.codec.compute_visual_diff",
        lambda *_args, **_kwargs: VisualDiffResult(
            has_visual_change=True,
            change_fraction=0.08,
            summary="canvas region changed",
        ),
    )

    route = choose_route(step, tmp_run_folder)

    assert route == "crop_with_context"
