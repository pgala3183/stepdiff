"""Synthetic routing test cases — no browser required."""

from __future__ import annotations

from typing import Any

Case = dict[str, Any]


def _case(
    case_id: str,
    *,
    before: str,
    after: str,
    expected_route: str,
    visual_change: bool = False,
    before_nodes: list[dict] | None = None,
    after_nodes: list[dict] | None = None,
    description: str = "",
) -> Case:
    return {
        "id": case_id,
        "description": description,
        "before_text": before,
        "after_text": after,
        "before_nodes": before_nodes or [],
        "after_nodes": after_nodes or [],
        "visual_change": visual_change,
        "expected_route": expected_route,
    }


def build_routing_cases() -> list[Case]:
    cases: list[Case] = []

    # --- validation errors always text_only ---
    for i, msg in enumerate(
        [
            "Email is required",
            "Invalid email address",
            "An error occurred",
            "You must accept terms",
            "Please enter your name",
        ]
    ):
        cases.append(
            _case(
                f"error_{i}",
                before="Email\nPassword\nSubmit",
                after=f"Email\n{msg}\nPassword\nSubmit",
                expected_route="text_only",
                visual_change=True,
                description=f"error keyword: {msg}",
            )
        )

    # --- structural DOM changes → text_only even with visual ---
    cases.append(
        _case(
            "checkout_button_enabled",
            before="Email\ntest@example.com\n- button \"Checkout\" [disabled]",
            after="Email\ntest@example.com\n- button \"Checkout\"",
            expected_route="text_only",
            visual_change=True,
            description="button enabled after form fill",
        )
    )
    cases.append(
        _case(
            "modal_dialog_appears",
            before="Checkout",
            after='Checkout\n- dialog "Order Summary"\n- button "Close"',
            expected_route="text_only",
            visual_change=True,
            after_nodes=[
                {"role": "dialog", "name": "Order Summary", "value": None, "bbox": None},
            ],
            description="modal dialog in DOM text",
        )
    )
    cases.append(
        _case(
            "new_alert_removed",
            before="Email\n- alert: Email is required",
            after="Email\ntest@example.com",
            expected_route="text_only",
            visual_change=False,
            description="alert removed after typing email",
        )
    )
    cases.append(
        _case(
            "generic_new_text",
            before="Hello",
            after="Hello\nWorld",
            expected_route="text_only",
            visual_change=False,
            description="non-field new line",
        )
    )

    # --- value-only field updates + visual → crop_with_context ---
    for qty in ("2", "3", "5", "10"):
        cases.append(
            _case(
                f"spinbutton_qty_{qty}",
                before='- spinbutton "Quantity": "1"',
                after=f'- spinbutton "Quantity": "{qty}"',
                expected_route="crop_with_context",
                visual_change=True,
                before_nodes=[
                    {"role": "spinbutton", "name": "Quantity", "value": "1", "bbox": None},
                ],
                after_nodes=[
                    {"role": "spinbutton", "name": "Quantity", "value": qty, "bbox": None},
                ],
                description=f"quantity spinbutton {qty}",
            )
        )

    for email in ("a@b.co", "user@example.com", "demo@test.org"):
        safe = email.replace("@", "_at_").replace(".", "_")
        cases.append(
            _case(
                f"textbox_email_{safe}",
                before='- textbox "Email": ""',
                after=f'- textbox "Email": "{email}"',
                expected_route="crop_with_context",
                visual_change=True,
                before_nodes=[
                    {"role": "textbox", "name": "Email", "value": "", "bbox": None},
                ],
                after_nodes=[
                    {"role": "textbox", "name": "Email", "value": email, "bbox": None},
                ],
                description=f"email fill {email}",
            )
        )

    # --- pure visual, no DOM ---
    cases.append(
        _case(
            "visual_only_chart",
            before="Chart\nQuantity: 1",
            after="Chart\nQuantity: 1",
            expected_route="crop_with_context",
            visual_change=True,
            description="identical DOM, canvas pixels changed",
        )
    )

    # --- value swap lines (aria style) ---
    cases.append(
        _case(
            "aria_spinbutton_swap",
            before="Email\n- spinbutton \"Quantity\": \"1\"\n- button \"Checkout\" [disabled]",
            after="Email\n- spinbutton \"Quantity\": \"5\"\n- button \"Checkout\" [disabled]",
            expected_route="crop_with_context",
            visual_change=True,
            description="spinbutton line swap with unchanged button",
        )
    )

    # --- no visual: always text_only ---
    cases.append(
        _case(
            "dom_only_no_screenshots",
            before="A",
            after="A\nB",
            expected_route="text_only",
            visual_change=False,
            description="no screenshots available",
        )
    )

    # --- visual false, dom change ---
    for i in range(5):
        cases.append(
            _case(
                f"text_only_batch_{i}",
                before=f"Line {i}",
                after=f"Line {i}\nLine {i + 1}",
                expected_route="text_only",
                visual_change=False,
            )
        )

    cases.append(
        _case(
            "password_field_value",
            before='- textbox "Password": ""',
            after='- textbox "Password": "secret123"',
            expected_route="crop_with_context",
            visual_change=True,
            description="password textbox value update",
        )
    )

    return cases


ROUTING_CASES = build_routing_cases()
