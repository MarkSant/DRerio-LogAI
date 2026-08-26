"""Geometry helpers for ROI alignment and snapping logic."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

import structlog

log = structlog.get_logger()

Point = tuple[float, float]


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


#: Default Douglas-Peucker epsilon as a fraction of the contour perimeter.
#: 0.5% preserves the corners of a rectangular/octagonal tank while collapsing
#: the pixel jitter YOLO leaves along straight edges. Mirrors the default of
#: ``settings.yolo_model.aquarium_polygon_epsilon``.
DEFAULT_POLYGON_EPSILON_FACTOR = 0.005


def simplify_polygon(
    raw_polygon: Any,
    *,
    epsilon_factor: float = DEFAULT_POLYGON_EPSILON_FACTOR,
) -> list[list[int]]:
    """Reduce the vertex count of a segmentation mask outline.

    YOLO segmentation masks come back as the raw ``cv2.findContours`` contour —
    one vertex per boundary pixel, often 200+ points. Every downstream consumer
    (the editable polygon canvas, the ArenaROI parquet, the recorder overlay)
    wants a clean ~6-12 vertex polygon instead.

    Lives here rather than on a coordinator because BOTH auto-detection flows
    need it: the live burst path and the pre-recorded segmentation path. It was
    previously a private method of ``LiveCalibrationCoordinator``, which is why
    the pre-recorded flow shipped raw 200-vertex outlines while the live one
    shipped simplified ones for the same tank.

    Takes the epsilon FACTOR rather than a settings object so it stays a pure
    function — callers read ``settings.yolo_model.aquarium_polygon_epsilon``
    themselves and pass the number.

    Degrades to the raw outline (never raises, never returns fewer than the
    input's points) whenever simplification cannot be trusted: a zero-length
    perimeter, an approximation that collapses below a triangle, or any cv2
    failure. Losing the arena here would send the user to manual drawing despite
    the model having found the tank.

    Args:
        raw_polygon: ndarray-like of shape (N, 2) in pixel coordinates.
        epsilon_factor: Douglas-Peucker epsilon as a fraction of the perimeter.
            ``0.0`` disables simplification and returns the raw outline.

    Returns:
        Polygon as a list of ``[x, y]`` integer pairs.
    """
    import cv2
    import numpy as np

    def _as_int_pairs(polygon: Any) -> list[list[int]]:
        return [[int(point[0]), int(point[1])] for point in polygon]

    if epsilon_factor <= 0:
        return _as_int_pairs(raw_polygon)

    try:
        contour = np.asarray(raw_polygon, dtype=np.float32).reshape(-1, 1, 2)
        perimeter = float(cv2.arcLength(contour, closed=True))
        if perimeter <= 0:
            return _as_int_pairs(raw_polygon)

        epsilon = max(1.0, epsilon_factor * perimeter)
        approx = cv2.approxPolyDP(contour, epsilon, closed=True)

        if approx is None or len(approx) < 3:
            # Approximation collapsed below a triangle — keep the raw shape.
            return _as_int_pairs(raw_polygon)

        # ``approx`` has shape (N, 1, 2); ``.ravel()`` flattens each (1, 2)
        # entry so mypy resolves the dtype instead of seeing a scalar index.
        simplified = [[int(pt.ravel()[0]), int(pt.ravel()[1])] for pt in approx]
        log.info(
            "geometry.polygon_simplified",
            raw_vertices=len(raw_polygon),
            simplified_vertices=len(simplified),
            epsilon_factor=epsilon_factor,
            perimeter_px=round(perimeter, 1),
        )
        return simplified
    # except Exception justified: cv2 contour math over model output —
    # heterogeneous failures, and the raw outline is always a usable answer.
    except Exception:
        log.warning("geometry.polygon_simplify_failed", exc_info=True)
        return _as_int_pairs(raw_polygon)


def resolve_polygon_epsilon_factor(settings_obj: Any) -> float:
    """Read ``yolo_model.aquarium_polygon_epsilon``, falling back to the default.

    Both auto-detection flows need this exact lookup, and both must tolerate a
    stripped settings object (tests, partial configs) without losing the
    detection.
    """
    try:
        return float(
            getattr(
                getattr(settings_obj, "yolo_model", None),
                "aquarium_polygon_epsilon",
                DEFAULT_POLYGON_EPSILON_FACTOR,
            )
        )
    # except Exception justified: settings may be a stub in tests — the default
    # is always a valid answer.
    except Exception:
        log.debug("geometry.polygon_epsilon.settings_fallback", exc_info=True)
        return DEFAULT_POLYGON_EPSILON_FACTOR
