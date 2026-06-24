"""DOM and accessibility tree diffing."""

from __future__ import annotations

from dataclasses import dataclass, field

from stepdiff.compaction.types import DomDiff
from stepdiff.schemas import StepState

_ERROR_KEYWORDS = ("required", "invalid", "error", "please", "must")
_MODAL_ROLES = frozenset({"dialog", "alertdialog"})
_MODAL_NAME_KEYWORDS = ("modal", "dialog", "checkout")
_FORM_FIELD_ROLES = frozenset({"textbox", "combobox", "spinbutton", "checkbox"})


@dataclass
class DomDiffResult:
    has_changes: bool
    new_text: list[str] = field(default_factory=list)
    removed_text: list[str] = field(default_factory=list)
    changed_values: list[tuple[str, str]] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.3


@dataclass
class NodeDiffResult:
    new_nodes: list[dict] = field(default_factory=list)
    removed_nodes: list[dict] = field(default_factory=list)
    has_modal: bool = False
    has_form_fields: bool = False
    summary: str = ""


def _text_lines(state: StepState) -> set[str]:
    return {line.strip() for line in state.dom_text.splitlines() if line.strip()}


def _node_key(node: dict) -> tuple[str, str]:
    return (str(node.get("role", "")), str(node.get("name", "")))


def _node_map(nodes: list[dict]) -> dict[tuple[str, str], dict]:
    return {_node_key(node): node for node in nodes}


def _field_label(role: str, name: str) -> str:
    if name:
        return f"{role}: {name}"
    return role


def _is_error_message(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _ERROR_KEYWORDS)


def _format_value_change(old_value: object, new_value: object) -> str:
    old = "" if old_value is None else str(old_value)
    new = "" if new_value is None else str(new_value)
    return f"{old}->{new}"


_FIELD_VALUE_ROLES = frozenset(
    {"textbox", "spinbutton", "combobox", "searchbox", "checkbox", "radio"}
)
_STRUCTURAL_TEXT_KEYWORDS = frozenset(
    {"dialog", "modal", "alert", "button", "link", "heading", "banner", "main"}
)


def _new_text_is_value_only(lines: list[str]) -> bool:
    """True when added lines only reflect form field value updates (not modals/buttons)."""
    if not lines:
        return True
    for line in lines:
        lower = line.lower()
        if _is_error_message(line):
            return False
        if any(role in lower for role in _FIELD_VALUE_ROLES):
            continue
        if any(keyword in lower for keyword in _STRUCTURAL_TEXT_KEYWORDS):
            return False
        return False
    return True


def _is_value_swap(text_diff: DomDiffResult) -> bool:
    """Field value edits that replace one value-only line with another (e.g. spinbutton 1 → 5)."""
    if not text_diff.new_text or not text_diff.removed_text:
        return False
    return _new_text_is_value_only(text_diff.new_text) and _new_text_is_value_only(
        text_diff.removed_text
    )


def _is_field_value_update(text_diff: DomDiffResult) -> bool:
    """DOM diff is limited to form field value changes (candidate for visual crop route)."""
    if text_diff.changed_values and not text_diff.new_text and not text_diff.removed_text:
        return True
    if text_diff.changed_values and text_diff.new_text and not text_diff.removed_text:
        return _new_text_is_value_only(text_diff.new_text)
    if _is_value_swap(text_diff):
        return True
    return False


def dom_prefers_text_route(text_diff: DomDiffResult) -> bool:
    """Whether text_only should win over crop_with_context for this DOM diff."""
    if text_diff.error_messages:
        return True
    if _is_field_value_update(text_diff):
        return False
    if text_diff.removed_text:
        return True
    if text_diff.new_text and not _new_text_is_value_only(text_diff.new_text):
        return True
    return False


def diff_dom_text(before: StepState, after: StepState) -> DomDiffResult:
    before_lines = _text_lines(before)
    after_lines = _text_lines(after)

    new_text = sorted(after_lines - before_lines)
    removed_text = sorted(before_lines - after_lines)
    error_messages = [line for line in new_text if _is_error_message(line)]

    before_nodes = _node_map(before.dom_nodes)
    after_nodes = _node_map(after.dom_nodes)
    changed_values: list[tuple[str, str]] = []

    for key, after_node in after_nodes.items():
        before_node = before_nodes.get(key)
        if before_node is None:
            continue
        old_value = before_node.get("value")
        new_value = after_node.get("value")
        if old_value != new_value:
            label = _field_label(key[0], key[1])
            changed_values.append((label, _format_value_change(old_value, new_value)))

    has_changes = bool(new_text or removed_text or changed_values)

    if error_messages:
        summary = f"Validation error appeared: {error_messages[0]}"
        confidence = 0.95
    elif new_text:
        preview = ", ".join(new_text[:3])
        summary = f"New text appeared: {preview}"
        confidence = 0.85
    elif changed_values:
        pairs = "; ".join(f"{field} {change}" for field, change in changed_values[:3])
        summary = f"Field updated: {pairs}"
        confidence = 0.7
    else:
        summary = "No significant text change"
        confidence = 0.3

    return DomDiffResult(
        has_changes=has_changes,
        new_text=new_text,
        removed_text=removed_text,
        changed_values=changed_values,
        error_messages=error_messages,
        summary=summary,
        confidence=confidence,
    )


def _is_modal_node(node: dict) -> bool:
    role = str(node.get("role", "")).lower()
    name = str(node.get("name", "")).lower()
    if role in _MODAL_ROLES:
        return True
    return any(keyword in name for keyword in _MODAL_NAME_KEYWORDS)


def _is_form_field_node(node: dict) -> bool:
    return str(node.get("role", "")).lower() in _FORM_FIELD_ROLES


def _build_node_summary(
    new_nodes: list[dict],
    removed_nodes: list[dict],
    *,
    has_modal: bool,
    has_form_fields: bool,
) -> str:
    parts: list[str] = []

    if has_modal:
        parts.append("A modal or dialog appeared")
    if has_form_fields:
        parts.append("Form fields appeared")
    if new_nodes and not parts:
        labels = [_field_label(str(n.get("role", "")), str(n.get("name", ""))) for n in new_nodes[:3]]
        parts.append(f"New elements: {', '.join(labels)}")
    if removed_nodes:
        labels = [_field_label(str(n.get("role", "")), str(n.get("name", ""))) for n in removed_nodes[:3]]
        parts.append(f"Removed elements: {', '.join(labels)}")

    if not parts:
        return "No structural node changes"
    return ". ".join(parts) + "."


def diff_dom_nodes(before: StepState, after: StepState) -> NodeDiffResult:
    before_nodes = _node_map(before.dom_nodes)
    after_nodes = _node_map(after.dom_nodes)

    before_keys = set(before_nodes)
    after_keys = set(after_nodes)

    new_nodes = [after_nodes[key] for key in sorted(after_keys - before_keys)]
    removed_nodes = [before_nodes[key] for key in sorted(before_keys - after_keys)]

    has_modal = any(_is_modal_node(node) for node in new_nodes)
    has_form_fields = any(_is_form_field_node(node) for node in new_nodes)

    summary = _build_node_summary(
        new_nodes,
        removed_nodes,
        has_modal=has_modal,
        has_form_fields=has_form_fields,
    )

    return NodeDiffResult(
        new_nodes=new_nodes,
        removed_nodes=removed_nodes,
        has_modal=has_modal,
        has_form_fields=has_form_fields,
        summary=summary,
    )


def diff_dom(before: StepState, after: StepState) -> DomDiff:
    """Legacy combined diff used by compaction routes."""
    text_result = diff_dom_text(before, after)
    node_result = diff_dom_nodes(before, after)

    changed_text = text_result.new_text + text_result.removed_text
    added_labels = [
        _field_label(str(node.get("role", "")), str(node.get("name", "")))
        for node in node_result.new_nodes
    ]
    removed_labels = [
        _field_label(str(node.get("role", "")), str(node.get("name", "")))
        for node in node_result.removed_nodes
    ]

    summary_parts = [text_result.summary]
    if node_result.summary != "No structural node changes":
        summary_parts.append(node_result.summary)

    return DomDiff(
        added_nodes=(text_result.new_text + added_labels)[:50],
        removed_nodes=(text_result.removed_text + removed_labels)[:50],
        changed_text=changed_text[:50],
        summary=" ".join(summary_parts),
    )
