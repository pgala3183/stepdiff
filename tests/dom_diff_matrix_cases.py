"""Synthetic DOM diff test cases."""

from __future__ import annotations

from typing import Any

Case = dict[str, Any]


def _case(
    case_id: str,
    *,
    before: str,
    after: str,
    expect_errors: list[str] | None = None,
    expect_new: list[str] | None = None,
    expect_modal: bool = False,
    min_confidence: float | None = None,
    description: str = "",
) -> Case:
    return {
        "id": case_id,
        "description": description,
        "before_text": before,
        "after_text": after,
        "expect_errors": expect_errors or [],
        "expect_new": expect_new or [],
        "expect_modal": expect_modal,
        "min_confidence": min_confidence,
    }


def build_dom_diff_cases() -> list[Case]:
    cases: list[Case] = [
        _case(
            "validation_required",
            before="Email\nPassword",
            after="Email\nEmail is required\nPassword",
            expect_errors=["Email is required"],
            min_confidence=0.95,
        ),
        _case(
            "validation_invalid",
            before="Email",
            after="Email\nInvalid email address",
            expect_errors=["Invalid email address"],
            min_confidence=0.95,
        ),
        _case(
            "simple_new_line",
            before="Hello",
            after="Hello\nWorld",
            expect_new=["World"],
            min_confidence=0.85,
        ),
        _case(
            "no_change",
            before="Same",
            after="Same",
        ),
    ]

    for i, msg in enumerate(["Field is required", "Must be numeric", "Please try again"]):
        cases.append(
            _case(
                f"error_variant_{i}",
                before="Form",
                after=f"Form\n{msg}",
                expect_errors=[msg],
                min_confidence=0.95,
            )
        )

    for word in ("World", "Footer", "Sidebar", "Banner text"):
        cases.append(
            _case(
                f"new_text_{word.lower().replace(' ', '_')}",
                before="Header",
                after=f"Header\n{word}",
                expect_new=[word],
            )
        )

    cases.append(
        _case(
            "modal_node",
            before="",
            after="",
            expect_modal=True,
            description="dialog node added",
        )
    )

    return cases


DOM_DIFF_CASES = build_dom_diff_cases()

# Modal case uses nodes — override in test via after_nodes fixture field
DOM_DIFF_CASES[-1]["before_nodes"] = []
DOM_DIFF_CASES[-1]["after_nodes"] = [
    {"role": "dialog", "name": "Confirm", "value": None, "bbox": None},
]
