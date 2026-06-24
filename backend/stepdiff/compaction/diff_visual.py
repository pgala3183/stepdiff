"""Screenshot diff using Pillow and NumPy."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from stepdiff.compaction.types import BoundingBox, VisualDiff
from stepdiff.schemas import StepState

SCREENSHOT_BASELINE_TOKENS = 1200
_PIXEL_THRESHOLD = 30
_MIN_REGION_AREA = 400
_CHANGE_FRACTION_THRESHOLD = 0.02
_SSIM_CHANGE_THRESHOLD = 0.95
_CROP_PADDING = 20
_BLOCK_SIZE = 8
_C1 = 0.01**2
_C2 = 0.03**2


@dataclass
class BBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class VisualDiffResult:
    has_visual_change: bool
    change_fraction: float
    changed_regions: list[BBox] = field(default_factory=list)
    ssim_score: float = 1.0
    dominant_change_region: BBox | None = None
    crop_paths: list[str] = field(default_factory=list)
    summary: str = ""


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_crop_tokens(bbox: BBox) -> int:
    return max(1, (bbox.width * bbox.height) // 200)


def _load_rgb_array(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def _align_images(before_arr: np.ndarray, after_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h = min(before_arr.shape[0], after_arr.shape[0])
    w = min(before_arr.shape[1], after_arr.shape[1])
    return before_arr[:h, :w], after_arr[:h, :w]


def crop_region(image_path: str, bbox: BBox, padding: int = 20) -> np.ndarray:
    image = _load_rgb_array(Path(image_path))
    height, width = image.shape[:2]

    x0 = max(0, bbox.x - padding)
    y0 = max(0, bbox.y - padding)
    x1 = min(width, bbox.x + bbox.width + padding)
    y1 = min(height, bbox.y + bbox.height + padding)

    return image[y0:y1, x0:x1]


def _block_ssim(block_a: np.ndarray, block_b: np.ndarray) -> float:
    a = block_a.astype(np.float64)
    b = block_b.astype(np.float64)
    if a.ndim == 3:
        a = a.mean(axis=2)
        b = b.mean(axis=2)

    mu1 = a.mean()
    mu2 = b.mean()
    sigma1_sq = a.var()
    sigma2_sq = b.var()
    sigma12 = ((a - mu1) * (b - mu2)).mean()

    numerator = (2 * mu1 * mu2 + _C1) * (2 * sigma12 + _C2)
    denominator = (mu1**2 + mu2**2 + _C1) * (sigma1_sq + sigma2_sq + _C2)
    if denominator == 0:
        return 1.0
    return float(numerator / denominator)


def _compute_ssim(before_arr: np.ndarray, after_arr: np.ndarray) -> float:
    h, w = before_arr.shape[:2]
    scores: list[float] = []

    if h < _BLOCK_SIZE or w < _BLOCK_SIZE:
        return _block_ssim(before_arr, after_arr)

    for y in range(0, h - _BLOCK_SIZE + 1, _BLOCK_SIZE):
        for x in range(0, w - _BLOCK_SIZE + 1, _BLOCK_SIZE):
            block_a = before_arr[y : y + _BLOCK_SIZE, x : x + _BLOCK_SIZE]
            block_b = after_arr[y : y + _BLOCK_SIZE, x : x + _BLOCK_SIZE]
            scores.append(_block_ssim(block_a, block_b))

    return float(np.mean(scores)) if scores else 1.0


def _flood_fill_label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    current_label = 0

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or labels[y, x] != 0:
                continue
            current_label += 1
            queue: deque[tuple[int, int]] = deque([(y, x)])
            labels[y, x] = current_label
            while queue:
                cy, cx = queue.popleft()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = current_label
                        queue.append((ny, nx))

    return labels, current_label


def _label_connected_regions(mask: np.ndarray) -> tuple[np.ndarray, int]:
    try:
        from scipy.ndimage import label  # type: ignore[import-untyped]

        return label(mask)
    except ImportError:
        return _flood_fill_label(mask)


def _regions_from_labels(labels: np.ndarray, mask: np.ndarray) -> list[BBox]:
    regions: list[BBox] = []
    for label_id in range(1, int(labels.max()) + 1):
        ys, xs = np.where((labels == label_id) & mask)
        if ys.size == 0:
            continue
        area = int(ys.size)
        if area < _MIN_REGION_AREA:
            continue
        x0 = int(xs.min())
        y0 = int(ys.min())
        x1 = int(xs.max()) + 1
        y1 = int(ys.max()) + 1
        regions.append(BBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0))

    regions.sort(key=lambda box: box.area, reverse=True)
    return regions


def _build_summary(change_fraction: float, region_count: int, ssim_score: float, has_change: bool) -> str:
    pct = round(change_fraction * 100, 2)
    if not has_change:
        return f"No significant visual change detected (changed {pct}% of pixels, SSIM {ssim_score:.2f})."
    region_word = "region" if region_count == 1 else "regions"
    return (
        f"Visual change detected: {pct}% of pixels changed across "
        f"{region_count} {region_word} (SSIM {ssim_score:.2f})."
    )


def compute_visual_diff(before_path: str, after_path: str, run_folder: Path) -> VisualDiffResult:
    before_file = Path(before_path)
    after_file = Path(after_path)
    if not before_file.is_absolute():
        before_file = run_folder / before_file
    if not after_file.is_absolute():
        after_file = run_folder / after_file

    if not before_file.exists() or not after_file.exists():
        return VisualDiffResult(
            has_visual_change=False,
            change_fraction=0.0,
            ssim_score=1.0,
            summary="Screenshot files not found.",
        )

    before_arr, after_arr = _align_images(_load_rgb_array(before_file), _load_rgb_array(after_file))

    diff = np.abs(after_arr.astype(np.int16) - before_arr.astype(np.int16))
    mask = diff.max(axis=2) > _PIXEL_THRESHOLD
    change_fraction = float(mask.sum() / mask.size) if mask.size else 0.0
    ssim_score = _compute_ssim(before_arr, after_arr)

    labels, _ = _label_connected_regions(mask)
    changed_regions = _regions_from_labels(labels, mask)
    dominant_change_region = changed_regions[0] if changed_regions else None

    crops_dir = run_folder / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    crop_paths: list[str] = []

    for index, region in enumerate(changed_regions):
        crop_arr = crop_region(str(after_file), region, padding=_CROP_PADDING)
        crop_rel = f"crops/crop_{index}.png"
        crop_abs = run_folder / crop_rel
        Image.fromarray(crop_arr).save(crop_abs)
        crop_paths.append(crop_rel)

    has_visual_change = change_fraction > _CHANGE_FRACTION_THRESHOLD or ssim_score < _SSIM_CHANGE_THRESHOLD
    summary = _build_summary(change_fraction, len(changed_regions), ssim_score, has_visual_change)

    return VisualDiffResult(
        has_visual_change=has_visual_change,
        change_fraction=round(change_fraction, 6),
        changed_regions=changed_regions,
        ssim_score=round(ssim_score, 4),
        dominant_change_region=dominant_change_region,
        crop_paths=crop_paths,
        summary=summary,
    )


def _ocr_crop_text(image_path: str, bbox: BBox, *, padding: int = _CROP_PADDING) -> str | None:
    """Run Tesseract OCR on a crop; return None if Tesseract is unavailable."""
    try:
        import pytesseract
        from pytesseract import TesseractNotFoundError
    except ImportError:
        return None
    try:
        crop = crop_region(image_path, bbox, padding=padding)
        text = pytesseract.image_to_string(Image.fromarray(crop)).strip()
        return text or None
    except (TesseractNotFoundError, OSError):
        return None


def diff_screenshots(
    before: StepState,
    after: StepState,
    *,
    run_dir: Path | None = None,
    diff_output_path: Path | None = None,
    threshold: int = 30,
    run_ocr: bool = False,
) -> VisualDiff:
    del threshold  # kept for backward-compatible signature

    if not before.screenshot_path or not after.screenshot_path or run_dir is None:
        return VisualDiff()

    result = compute_visual_diff(before.screenshot_path, after.screenshot_path, run_dir)

    bounding_box: BoundingBox | None = None
    if result.dominant_change_region:
        dom = result.dominant_change_region
        bounding_box = BoundingBox(x=dom.x, y=dom.y, width=dom.width, height=dom.height)

    diff_image_path = result.crop_paths[0] if result.crop_paths else None
    if diff_output_path and result.has_visual_change:
        diff_output_path.parent.mkdir(parents=True, exist_ok=True)
        before_file = run_dir / before.screenshot_path
        after_file = run_dir / after.screenshot_path
        if before_file.exists() and after_file.exists():
            before_arr, after_arr = _align_images(
                _load_rgb_array(before_file),
                _load_rgb_array(after_file),
            )
            highlight = after_arr.copy()
            pixel_diff = np.abs(after_arr.astype(np.int16) - before_arr.astype(np.int16))
            changed = pixel_diff.max(axis=2) > _PIXEL_THRESHOLD
            highlight[changed] = [255, 0, 0]
            Image.fromarray(highlight).save(diff_output_path)
            diff_image_path = str(diff_output_path.relative_to(run_dir))

    ocr_text: str | None = None
    if run_ocr and bounding_box and result.dominant_change_region:
        after_file = run_dir / after.screenshot_path
        if after_file.exists():
            ocr_text = _ocr_crop_text(str(after_file), result.dominant_change_region)

    changed_pixels = 0
    if result.change_fraction:
        after_file = run_dir / after.screenshot_path
        if after_file.exists():
            after_shape = _load_rgb_array(after_file).shape
            changed_pixels = int(round(result.change_fraction * after_shape[0] * after_shape[1]))

    return VisualDiff(
        changed_pixels=changed_pixels,
        change_ratio=result.change_fraction,
        bounding_box=bounding_box,
        diff_image_path=diff_image_path,
        ocr_text=ocr_text,
    )
