"""Single rule for WHICH detection in a frame is the arena, and what counts as a usable outline.

Two flows pick an arena candidate out of a YOLO result, and until this module they
implemented the same idea twice:

* the LIVE camera path — ``LiveCalibrationCoordinator._select_box_index`` — ranked
  boxes by descending confidence and took the first one inside an area gate;
* the PRE-RECORDED path — ``AquariumDetector._extract_polygon_from_detection`` —
  did the same for boxes, but its segmentation branch had no ranking at all: it
  accepted the frame only when the model returned EXACTLY ONE mask.

That last asymmetry is what this module exists to remove. A real run (2026-08-31,
``cest_9.mp4``) produced two masks per frame — the tank at 0.928 confidence with 413
vertices, and a zero-height sliver on the bottom edge at 0.272 — and the "exactly
one" gate threw both away, degrading a segmentation run to a bounding box that
covered 93% of the frame. The user had explicitly asked to preserve the real mask
shape.

Everything here is a PURE FUNCTION over already-normalized inputs. That is
deliberate: the two call sites receive genuinely different result shapes — live
passes ``results[0].boxes.xyxy.cpu().numpy()`` plus a ``boxes.conf`` tensor, while
the pre-recorded detector passes a plain sequence of box objects exposing ``.conf``
and ``.xyxy[0]``. Each site keeps its own normalization; only the RULE is shared.
The same split already worked for ``utils.geometry.simplify_polygon``.

Nothing here raises. A candidate that cannot be evaluated is kept, never dropped —
losing the arena sends the researcher to manual drawing, which is strictly worse
than passing a questionable outline to the validation that runs downstream anyway.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = [
    "DEFAULT_MAX_AREA_RATIO",
    "DEFAULT_MIN_AREA_RATIO",
    "is_degenerate_outline",
    "rank_box_indices",
    "select_best_box_index",
]

#: Below this fraction of the frame the box is a fish, a reflection or a label —
#: not a tank. Matches the historical ``min_area_ratio`` of both flows.
DEFAULT_MIN_AREA_RATIO = 0.1

#: Above this fraction the box is the whole field of view, which is a false
#: positive rather than an arena. Matches the historical ``max_area_ratio``.
DEFAULT_MAX_AREA_RATIO = 0.98


def _box_area(box: Sequence[float]) -> float:
    """Area of one ``(x1, y1, x2, y2)`` box, or ``0.0`` when unreadable."""
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (IndexError, TypeError, ValueError):
        return 0.0
    return abs(x2 - x1) * abs(y2 - y1)


def rank_box_indices(
    confidences: Sequence[float] | None,
    boxes_xyxy: Sequence[Sequence[float]],
    frame_width: int,
    frame_height: int,
    *,
    min_area_ratio: float = DEFAULT_MIN_AREA_RATIO,
    max_area_ratio: float = DEFAULT_MAX_AREA_RATIO,
) -> list[int]:
    """Indices of every box that passes the area gate, best candidate first.

    Boxes are considered in DESCENDING CONFIDENCE. Returning the whole ranked
    list rather than only the winner lets a caller walk to the next-best
    candidate when the top one turns out to be unusable for a reason this
    function cannot see (no mask at that index, for instance).

    Ordering falls back to descending AREA when confidences are missing or do
    not line up with the boxes, so a model or test double that exposes no
    ``conf`` still yields a ranking instead of nothing.

    Args:
        confidences: One confidence per box, or ``None`` when unavailable.
        boxes_xyxy: Boxes as ``(x1, y1, x2, y2)`` in pixels.
        frame_width: Frame width in pixels.
        frame_height: Frame height in pixels.
        min_area_ratio: Area floor as a fraction of the frame.
        max_area_ratio: Area ceiling as a fraction of the frame.

    Returns:
        Ranked list of indices into ``boxes_xyxy``. Empty when nothing qualifies.
    """
    frame_area = float(frame_width) * float(frame_height)
    if frame_area <= 0 or not len(boxes_xyxy):
        return []

    count = len(boxes_xyxy)
    use_confidence = confidences is not None and len(confidences) == count
    if use_confidence:
        assert confidences is not None  # narrowed by ``use_confidence``
        order = sorted(range(count), key=lambda i: float(confidences[i]), reverse=True)
    else:
        order = sorted(range(count), key=lambda i: _box_area(boxes_xyxy[i]), reverse=True)

    ranked = [
        idx
        for idx in order
        if min_area_ratio <= (_box_area(boxes_xyxy[idx]) / frame_area) <= max_area_ratio
    ]

    log.debug(
        "arena_candidate_selection.ranked",
        total_boxes=count,
        accepted=len(ranked),
        ordered_by="confidence" if use_confidence else "area",
    )
    return ranked


def select_best_box_index(
    confidences: Sequence[float] | None,
    boxes_xyxy: Sequence[Sequence[float]],
    frame_width: int,
    frame_height: int,
    *,
    min_area_ratio: float = DEFAULT_MIN_AREA_RATIO,
    max_area_ratio: float = DEFAULT_MAX_AREA_RATIO,
) -> int | None:
    """Index of the single best box, or ``None`` when none passes the area gate."""
    ranked = rank_box_indices(
        confidences,
        boxes_xyxy,
        frame_width,
        frame_height,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
    )
    return ranked[0] if ranked else None


def is_degenerate_outline(polygon: Any) -> bool:
    """True when an outline cannot describe an area and must not be a candidate.

    Two shapes qualify, and both were observed in production:

    * fewer than 3 vertices — not a polygon at all;
    * a bounding box with zero width or zero height — the sliver YOLO emits on a
      frame edge. In the 2026-08-31 run this arrived as a 4-point mask with
      ``bbox=[76, 720, 1042, 720]`` and area 0, and it was enough to disqualify
      the frame that also carried the real tank.

    Anything this function cannot evaluate is reported as NOT degenerate. Being
    wrong in that direction costs one extra candidate that downstream area and
    confidence validation will reject anyway; being wrong in the other direction
    silently discards a real arena.
    """
    if polygon is None:
        return True
    try:
        if len(polygon) < 3:
            return True
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
    except (IndexError, TypeError, ValueError):
        log.debug("arena_candidate_selection.degenerate_check.unreadable", exc_info=True)
        return False

    return (max(xs) - min(xs)) <= 0 or (max(ys) - min(ys)) <= 0
