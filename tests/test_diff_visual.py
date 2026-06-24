"""Tests for visual diffing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from stepdiff.compaction.diff_visual import (
    BBox,
    compute_visual_diff,
    crop_region,
    diff_screenshots,
    estimate_crop_tokens,
)
from stepdiff.schemas import StepState


def _write_solid_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (100, 100)) -> None:
    Image.fromarray(np.full((*size, 3), color, dtype=np.uint8)).save(path)


def test_identical_images_have_no_visual_change(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _write_solid_image(before, (120, 120, 120))
    _write_solid_image(after, (120, 120, 120))

    result = compute_visual_diff(str(before), str(after), tmp_path)
    assert result.has_visual_change is False
    assert result.change_fraction == 0.0
    assert result.ssim_score == pytest.approx(1.0, abs=0.05)
    assert result.changed_regions == []


def test_changed_region_is_detected_and_cropped(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _write_solid_image(before, (255, 255, 255), size=(120, 120))

    after_arr = np.full((120, 120, 3), 255, dtype=np.uint8)
    after_arr[40:80, 40:80] = [0, 0, 255]
    Image.fromarray(after_arr).save(after)

    result = compute_visual_diff(str(before), str(after), tmp_path)
    assert result.has_visual_change is True
    assert result.change_fraction > 0.02
    assert len(result.changed_regions) >= 1
    assert result.dominant_change_region is not None
    assert result.crop_paths
    assert (tmp_path / result.crop_paths[0]).exists()
    assert "Visual change detected" in result.summary


def test_crop_region_with_padding(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[30:50, 30:50] = [255, 0, 0]
    Image.fromarray(arr).save(image)

    bbox = BBox(x=30, y=30, width=20, height=20)
    crop = crop_region(str(image), bbox, padding=10)
    assert crop.shape[0] == 40
    assert crop.shape[1] == 40


def test_estimate_crop_tokens() -> None:
    bbox = BBox(x=0, y=0, width=200, height=100)
    assert estimate_crop_tokens(bbox) == 100


def test_ocr_crop_text_handles_missing_tesseract(tmp_path: Path, monkeypatch) -> None:
    import pytesseract
    from pytesseract import TesseractNotFoundError

    from stepdiff.compaction.diff_visual import _ocr_crop_text

    image = tmp_path / "image.png"
    _write_solid_image(image, (255, 255, 255), size=(40, 40))
    bbox = BBox(x=0, y=0, width=40, height=40)

    def _missing(*_args, **_kwargs):
        raise TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", _missing)

    assert _ocr_crop_text(str(image), bbox) is None


def test_diff_screenshots_continues_when_ocr_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _write_solid_image(before, (255, 255, 255), size=(120, 120))
    after_arr = np.full((120, 120, 3), 255, dtype=np.uint8)
    after_arr[40:80, 40:80] = [0, 0, 255]
    Image.fromarray(after_arr).save(after)

    monkeypatch.setattr(
        "stepdiff.compaction.diff_visual._ocr_crop_text",
        lambda *_args, **_kwargs: None,
    )

    before_state = StepState(
        url="http://localhost/",
        title="Test",
        screenshot_path="before.png",
        dom_text="",
        dom_nodes=[],
        timestamp=0.0,
    )
    after_state = before_state.model_copy(update={"screenshot_path": "after.png"})

    result = diff_screenshots(
        before_state,
        after_state,
        run_dir=tmp_path,
        run_ocr=True,
    )

    assert result.change_ratio > 0
    assert result.ocr_text is None
