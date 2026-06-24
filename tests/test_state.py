"""Tests for page state capture helpers."""

from __future__ import annotations

import time

from stepdiff.browser.state import _build_dom_text, _flatten_tree, estimate_tokens
from stepdiff.schemas import BrowserAction, StepRecord, StepState


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 100) == 25


def test_flatten_tree_skips_generic_roles() -> None:
    tree = {
        "role": "generic",
        "children": [
            {"role": "button", "name": "Submit"},
            {"role": "text", "name": "Hello"},
        ],
    }
    parts = _flatten_tree(tree)
    assert "button: Submit" in parts
    assert "Hello" in parts


def test_flatten_tree_respects_depth_limit() -> None:
    node: dict = {"role": "text", "name": "deep"}
    current = node
    for i in range(10):
        child = {"role": "text", "name": f"level-{i}"}
        current["children"] = [child]
        current = child
    text = _build_dom_text(node)
    assert "level-4" in text or "level-3" in text


def test_step_state_model() -> None:
    state = StepState(
        url="http://localhost/",
        title="Test",
        screenshot_path="screenshots/step_000_before.png",
        dom_text="Hello",
        dom_nodes=[{"role": "button", "name": "Submit", "value": None, "bbox": None}],
        timestamp=time.time(),
    )
    assert state.dom_text == "Hello"
    assert state.model_config.get("from_attributes") is True


def test_browser_action_and_step_record() -> None:
    action = BrowserAction(
        type="click",
        selector="#btn",
        value=None,
        description="Click #btn",
    )
    ts = time.time()
    state = StepState(
        url="http://localhost/",
        title="Test",
        dom_text="",
        dom_nodes=[],
        timestamp=ts,
    )
    record = StepRecord(
        step_id="step_001",
        action=action,
        before=state,
        after=state,
        run_id="run_abc",
    )
    assert record.step_id == "step_001"
    assert record.action.type == "click"
