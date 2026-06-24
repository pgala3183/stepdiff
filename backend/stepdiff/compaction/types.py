"""Internal compaction types (not part of the public data contract)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class DomDiff:
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    changed_text: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class VisualDiff:
    changed_pixels: int = 0
    change_ratio: float = 0.0
    bounding_box: BoundingBox | None = None
    diff_image_path: str | None = None
    ocr_text: str | None = None
