"""Geometry helpers for ROI alignment and snapping logic."""

from __future__ import annotations

import math
from typing import Iterable, Sequence, Tuple

Point = Tuple[float, float]


def polygon_centroid(points: Sequence[Point]) -> Point | None:
    """Return the centroid of a polygon using the shoelace formula.

    Returns ``None`` when fewer than 3 points are supplied or the polygon area
    is zero. Coordinates are returned as floats.
    """

    if len(points) < 3:
        return None

    area_twice = 0.0
    cx = 0.0
    cy = 0.0
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        area_twice += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if math.isclose(area_twice, 0.0):
        return None

    area = area_twice / 2.0
    factor = 1 / (6.0 * area)
    return cx * factor, cy * factor


def snap_point_to_axes(
    point: Point,
    *,
    anchors: Iterable[Point] | None = None,
    centers: Iterable[Point] | None = None,
    threshold: float = 8.0,
) -> Point | None:
    """Snap a point to the horizontal/vertical axes of anchors or centers.

    Args:
        point: The point to be adjusted.
        anchors: Iterable of anchor points (typically previous polygon vertices).
        centers: Iterable of "axis centers" used to project horizontal/vertical
            alignments (e.g., arena centroid).
        threshold: Maximum distance allowed to snap. Distances are computed as
            Euclidean distance between the original point and the candidate
            aligned point.

    Returns:
        A snapped point when a candidate lies within ``threshold`` units of the
        original point; otherwise ``None``.
    """

    px, py = point
    best_point: Point | None = None
    best_distance = threshold

    def _consider(candidate: Point) -> None:
        nonlocal best_point, best_distance
        cx, cy = candidate
        distance = math.hypot(cx - px, cy - py)
        if distance < best_distance:
            best_point = (cx, cy)
            best_distance = distance

    for anchor in anchors or []:
        ax, ay = anchor
        _consider((ax, py))  # Vertical alignment
        _consider((px, ay))  # Horizontal alignment

    for center in centers or []:
        cx, cy = center
        _consider((cx, py))  # Snap to vertical axis through center
        _consider((px, cy))  # Snap to horizontal axis through center
        _consider((cx, cy))  # Snap directly to center intersection

    return best_point
