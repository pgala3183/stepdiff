"""Parametrized DOM diff tests over a synthetic case matrix."""

from __future__ import annotations

import pytest

from stepdiff.compaction.diff_dom import diff_dom_nodes, diff_dom_text
from dom_diff_matrix_cases import DOM_DIFF_CASES


@pytest.mark.parametrize("case", DOM_DIFF_CASES, ids=[c["id"] for c in DOM_DIFF_CASES])
def test_dom_diff_matrix_case(case: dict, make_step_state) -> None:
    before = make_step_state(
        case["before_text"],
        case.get("before_nodes"),
    )
    after = make_step_state(
        case["after_text"],
        case.get("after_nodes"),
    )

    text_result = diff_dom_text(before, after)

    for msg in case.get("expect_errors", []):
        assert msg in text_result.error_messages, f"{case['id']}: missing error {msg!r}"

    for line in case.get("expect_new", []):
        assert line in text_result.new_text, f"{case['id']}: missing new text {line!r}"

    if case.get("min_confidence") is not None:
        assert text_result.confidence >= case["min_confidence"], (
            f"{case['id']}: confidence {text_result.confidence} "
            f"< {case['min_confidence']}"
        )

    if case.get("expect_modal"):
        node_result = diff_dom_nodes(before, after)
        assert node_result.has_modal is True, f"{case['id']}: expected modal"


def test_dom_diff_matrix_has_many_cases() -> None:
    assert len(DOM_DIFF_CASES) >= 10
