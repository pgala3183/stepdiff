"""Tests for DOM diff helpers."""

from __future__ import annotations

from stepdiff.compaction.diff_dom import (
    diff_dom_nodes,
    diff_dom_text,
    dom_prefers_text_route,
)


def test_diff_dom_text_detects_error_messages(make_step_state) -> None:
    before = make_step_state("Email\nPassword")
    after = make_step_state("Email\nEmail is required\nPassword")

    result = diff_dom_text(before, after)

    assert "Email is required" in result.error_messages
    assert result.confidence == 0.95


def test_diff_dom_text_detects_new_text(make_step_state) -> None:
    before = make_step_state("Hello")
    after = make_step_state("Hello\nWorld")

    result = diff_dom_text(before, after)

    assert result.new_text == ["World"]


def test_diff_dom_nodes_detects_modal_appearance(make_step_state) -> None:
    before = make_step_state("", nodes=[])
    after = make_step_state(
        "",
        nodes=[{"role": "dialog", "name": "Confirm", "value": None, "bbox": None}],
    )

    result = diff_dom_nodes(before, after)

    assert result.has_modal is True


def test_diff_dom_text_error_messages_have_high_confidence(make_step_state) -> None:
    before = make_step_state("Email\nPassword")
    after = make_step_state("Email\nEmail is required\nPassword")

    result = diff_dom_text(before, after)

    assert result.confidence == 0.95


def test_dom_prefers_text_route_for_modal_and_button_changes(make_step_state) -> None:
    before = make_step_state("Email\ntest@example.com")
    after = make_step_state('Email\ntest@example.com\n- button "Checkout"')

    result = diff_dom_text(before, after)

    assert dom_prefers_text_route(result) is True


def test_dom_prefers_text_route_false_for_value_only_spinbutton(make_step_state) -> None:
    before = make_step_state('- spinbutton "Quantity": "1"')
    after = make_step_state('- spinbutton "Quantity": "5"')

    result = diff_dom_text(before, after)

    assert result.new_text
    assert dom_prefers_text_route(result) is False


def test_dom_prefers_text_route_false_for_value_swap_lines(make_step_state) -> None:
    before = make_step_state(
        "Email\n- spinbutton \"Quantity\": \"1\"\n- button \"Checkout\" [disabled]"
    )
    after = make_step_state(
        "Email\n- spinbutton \"Quantity\": \"5\"\n- button \"Checkout\" [disabled]"
    )

    result = diff_dom_text(before, after)

    assert dom_prefers_text_route(result) is False
