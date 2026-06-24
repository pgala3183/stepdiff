"""Tests for Pydantic schema models."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from stepdiff.compaction.routes import compact_step
from stepdiff.schemas import BrowserAction, CompactObservation, StepRecord, StepState


def test_step_record_json_roundtrip() -> None:
    ts = time.time()
    state = StepState(
        url="http://localhost/checkout",
        title="Checkout",
        screenshot_path="screenshots/step_001_before.png",
        dom_text="Email\nPassword",
        dom_nodes=[{"role": "button", "name": "Submit", "value": None, "bbox": None}],
        timestamp=ts,
    )
    record = StepRecord(
        step_id="step_001",
        action=BrowserAction(
            type="click",
            selector="#submit",
            value=None,
            description="Click submit",
        ),
        before=state,
        after=state.model_copy(update={"dom_text": "Email\nPassword\nEmail is required"}),
        run_id="login_error",
    )

    payload = record.model_dump_json()
    restored = StepRecord.model_validate_json(payload)

    assert restored.step_id == record.step_id
    assert restored.run_id == record.run_id
    assert restored.action.type == "click"
    assert restored.before.dom_text == record.before.dom_text
    assert restored.after.dom_text == record.after.dom_text


def test_compact_observation_savings_pct(make_step_state) -> None:
    before = make_step_state("Hello")
    after = make_step_state("Hello\nWorld")
    obs = compact_step("step_001", before, after, "text_only")

    expected = round((1.0 - obs.token_estimate / obs.baseline_token_estimate) * 100.0, 2)
    assert obs.savings_pct == expected
    assert obs.savings_pct > 0.0


def test_browser_action_rejects_invalid_type() -> None:
    with pytest.raises(ValidationError):
        BrowserAction(
            type="hover",  # type: ignore[arg-type]
            selector="#btn",
            value=None,
            description="Invalid action",
        )


def test_compact_observation_model_accepts_valid_savings() -> None:
    obs = CompactObservation(
        step_id="step_001",
        route="text_only",
        content="DOM changes: test",
        crop_path=None,
        token_estimate=80,
        baseline_token_estimate=1200,
        confidence=0.85,
        savings_pct=93.33,
    )
    assert obs.savings_pct == 93.33
