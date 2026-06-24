"""Capture page state — DOM text, interactive nodes, and screenshot."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.async_api import Page

from stepdiff.schemas import StepState

_SKIP_ROLES = frozenset({"none", "presentation", "generic"})
_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "searchbox",
        "spinbutton",
        "switch",
    }
)
_TEXT_ROLES = frozenset({"text", "statictext", "paragraph", "heading"})
_MAX_DOM_TEXT_CHARS = 2000
_MAX_TREE_DEPTH = 5

_INTERACTIVE_SELECTOR = (
    "button, a[href], input, textarea, select, "
    "[role=button], [role=link], [role=checkbox], [role=textbox], "
    "[role=combobox], [role=radio], [role=switch], [role=tab], [role=searchbox]"
)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _flatten_tree(node: dict[str, Any], depth: int = 0) -> list[str]:
    if depth > _MAX_TREE_DEPTH:
        return []

    role = str(node.get("role", "")).lower()
    parts: list[str] = []

    if role not in _SKIP_ROLES:
        name = str(node.get("name", "")).strip()
        value = node.get("value")

        if role in _INTERACTIVE_ROLES:
            if name:
                parts.append(f"{role}: {name}")
            if value is not None and str(value).strip():
                parts.append(str(value))
        elif role in _TEXT_ROLES or (name and role not in _INTERACTIVE_ROLES):
            if name:
                parts.append(name)

    for child in node.get("children", []) or []:
        parts.extend(_flatten_tree(child, depth + 1))

    return parts


def _build_dom_text(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ""
    parts = _flatten_tree(snapshot)
    text = "\n".join(parts)
    if len(text) > _MAX_DOM_TEXT_CHARS:
        return text[:_MAX_DOM_TEXT_CHARS]
    return text


def _aria_snapshot_to_dom_text(aria_snapshot: str) -> str:
    if not aria_snapshot:
        return ""
    text = aria_snapshot.strip()
    if len(text) > _MAX_DOM_TEXT_CHARS:
        return text[:_MAX_DOM_TEXT_CHARS]
    return text


async def _capture_dom_text(page: Page) -> str:
    """Capture readable DOM text from the page accessibility tree."""
    accessibility = getattr(page, "accessibility", None)
    if accessibility is not None:
        snapshot = await accessibility.snapshot()
        return _build_dom_text(snapshot)

    aria_snapshot = await page.aria_snapshot()
    return _aria_snapshot_to_dom_text(aria_snapshot)


def _normalize_role(raw_role: str, tag: str, input_type: str | None) -> str:
    role = raw_role.lower() if raw_role else ""
    if role:
        return role
    tag = tag.lower()
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "textarea":
        return "textbox"
    if tag == "select":
        return "combobox"
    if tag == "input":
        type_map = {
            "checkbox": "checkbox",
            "radio": "radio",
            "submit": "button",
            "button": "button",
            "search": "searchbox",
        }
        return type_map.get(input_type or "", "textbox")
    return tag


async def _collect_interactive_nodes(page: Page) -> list[dict[str, Any]]:
    elements = await page.query_selector_all(_INTERACTIVE_SELECTOR)
    nodes: list[dict[str, Any]] = []

    for element in elements:
        bbox = await element.bounding_box()
        if bbox is None:
            continue

        meta = await element.evaluate(
            """(el) => {
                const label = el.getAttribute('aria-label')
                    || document.querySelector(`label[for="${el.id}"]`)?.innerText?.trim()
                    || el.getAttribute('placeholder')
                    || el.innerText?.trim()
                    || '';
                return {
                    role: el.getAttribute('role') || '',
                    tag: el.tagName.toLowerCase(),
                    inputType: el.getAttribute('type') || null,
                    name: label,
                    value: el.value ?? el.getAttribute('value') ?? null,
                };
            }"""
        )

        nodes.append(
            {
                "role": _normalize_role(meta["role"], meta["tag"], meta["inputType"]),
                "name": meta["name"],
                "value": meta["value"],
                "bbox": {
                    "x": round(bbox["x"], 1),
                    "y": round(bbox["y"], 1),
                    "width": round(bbox["width"], 1),
                    "height": round(bbox["height"], 1),
                },
            }
        )

    return nodes


async def capture_screenshot_bytes(page: Page) -> bytes:
    raw = await page.screenshot(full_page=True, type="png")
    image = Image.open(BytesIO(raw))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def capture_state(
    page: Page,
    run_folder: Path,
    screenshot_filename: str,
) -> StepState:
    screenshots_dir = run_folder / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    screenshot_abs = screenshots_dir / screenshot_filename
    screenshot_rel = f"screenshots/{screenshot_filename}"

    await page.screenshot(path=str(screenshot_abs), full_page=True, type="png")

    dom_text = await _capture_dom_text(page)
    dom_nodes = await _collect_interactive_nodes(page)

    return StepState(
        url=page.url,
        title=await page.title(),
        screenshot_path=screenshot_rel,
        dom_text=dom_text,
        dom_nodes=dom_nodes,
        timestamp=time.time(),
    )
