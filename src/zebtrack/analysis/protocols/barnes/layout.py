"""Rebuild a Barnes layout from the ROI names and polygons (ADR-014, CONTRACTS §6).

The names are the contract (``contract.expected_roi_names``); the
``ZoneData.metadata["barnes_layout"]`` cache never reaches the analysis (the
``ProtocolContext`` carries ROIs only, and the cache is in raw video pixels while
the context may be arena-local or warped). So the metrics ALWAYS rebuild:

* hole centres = centroids of the hole ROI polygons;
* the hole ring = ``cv2.fitEllipse`` of those centres (a circle through their mean
  when there are fewer than five holes, which ``fitEllipse`` cannot fit);
* the table = ``cv2.fitEllipse`` of the arena polygon (the ring when there is none);
* the "centre" disk of the search strategy = the ring scaled about its centre.

Pure: no Tk, no I/O. Every geometry stays in the space of the ROIs it came from.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

from zebtrack.analysis.protocols.barnes.contract import (
    QUADRANT_ROI,
    BarnesEllipse,
    BarnesHole,
    BarnesLayout,
    BarnesRoiKind,
    circular_offset,
    expected_roi_names,
    parse_barnes_roi_name,
)

if TYPE_CHECKING:
    from zebtrack.analysis.roi import ROI

__all__ = [
    "LayoutHole",
    "LayoutResolution",
    "ResolvedLayout",
    "points_in_scaled_ellipse",
    "resolve_layout",
]

logger = structlog.get_logger()

#: ``cv2.fitEllipse`` needs at least this many points.
_MIN_FIT_POINTS = 5
#: A fitted semi-axis below this (px) is degenerate: coincident centres, not a ring.
_MIN_SEMI_AXIS_PX = 1.0


@dataclass(frozen=True, slots=True)
class LayoutHole:
    """One hole ROI of the rebuilt layout.

    Attributes:
        offset: Signed offset from the target (``contract`` conventions).
        roi: The ROI as the report has it (name + shapely geometry).
        area_px: Area of the hole ROI — the denominator of a visit's cover.
    """

    offset: int
    roi: ROI
    area_px: float


@dataclass(frozen=True, slots=True)
class ResolvedLayout:
    """A Barnes layout rebuilt from the ROIs of one analysis.

    Attributes:
        layout: The contract's :class:`BarnesLayout` (``source="reconstructed"``,
            ``target_abs_index=0``: the absolute origin of a rebuilt layout is the
            target, so ``abs_index = offset mod n_holes``).
        holes: Every hole, sorted by ``abs_index``.
        quadrant: The ``quadrante_alvo`` ROI, ``None`` when it was not drawn.
    """

    layout: BarnesLayout
    holes: tuple[LayoutHole, ...]
    quadrant: ROI | None

    def in_center_disk(self, x: np.ndarray, y: np.ndarray, ratio: float) -> np.ndarray:
        """Which points lie inside the ring ellipse scaled by ``ratio`` about its centre."""
        return points_in_scaled_ellipse(self.layout.ring, x, y, ratio)


@dataclass(frozen=True, slots=True)
class LayoutResolution:
    """Outcome of :func:`resolve_layout`.

    Attributes:
        layout: The rebuilt layout, ``None`` when it cannot be rebuilt.
        missing: Required ROI names (``toca`` and every decoy) that are absent or
            have no area. Empty with ``layout=None`` means the holes exist but do
            not form a ring (degenerate geometry).
        duplicates: Barnes names drawn more than once, in stored order. The first
            ROI of each name is used; the caller warns about the others.
    """

    layout: ResolvedLayout | None
    missing: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()


def points_in_scaled_ellipse(
    ellipse: BarnesEllipse, x: np.ndarray, y: np.ndarray, ratio: float
) -> np.ndarray:
    """Boolean mask of the points inside ``ellipse`` scaled by ``ratio``.

    ``angle_deg`` follows OpenCV (rotation of the first semi-axis in image
    coordinates), so the test agrees with ``cv2.ellipse`` drawing the same ellipse.
    The boundary counts as inside.
    """
    cx, cy = ellipse.center_px
    a = ellipse.semi_axes_px[0] * ratio
    b = ellipse.semi_axes_px[1] * ratio
    theta = math.radians(ellipse.angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx = np.asarray(x, dtype=float) - cx
    dy = np.asarray(y, dtype=float) - cy
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    with np.errstate(invalid="ignore"):
        inside: np.ndarray = (u / a) ** 2 + (v / b) ** 2 <= 1.0
    return inside


def _fit_ellipse(points: np.ndarray) -> BarnesEllipse | None:
    """Ellipse through ``points`` (``(k, 2)``), or ``None`` when degenerate.

    Five or more points: ``cv2.fitEllipse``. Fewer: the circle centred on their mean
    with their mean distance as radius.
    """
    if len(points) >= _MIN_FIT_POINTS:
        (cx, cy), (width, height), angle = cv2.fitEllipse(points.astype(np.float32))
        values = (cx, cy, width, height, angle)
        if all(math.isfinite(v) for v in values) and min(width, height) / 2.0 >= _MIN_SEMI_AXIS_PX:
            return BarnesEllipse(
                center_px=(float(cx), float(cy)),
                semi_axes_px=(float(width) / 2.0, float(height) / 2.0),
                angle_deg=float(angle),
            )
    center = points.mean(axis=0)
    radius = float(np.hypot(*(points - center).T).mean()) if len(points) else 0.0
    if not math.isfinite(radius) or radius < _MIN_SEMI_AXIS_PX:
        return None
    return BarnesEllipse(
        center_px=(float(center[0]), float(center[1])),
        semi_axes_px=(radius, radius),
        angle_deg=0.0,
    )


def _usable(roi: ROI) -> bool:
    geometry = roi.geometry
    return geometry is not None and not geometry.is_empty and float(geometry.area) > 0.0


def resolve_layout(
    rois: Sequence[ROI],
    arena_polygon_px: Sequence[tuple[float, float]],
    n_holes: int,
) -> LayoutResolution:
    """Rebuild the layout of ``n_holes`` holes from the report's ROIs. Never raises.

    The first ROI of each Barnes name wins (stored order); later duplicates are
    ignored and reported in ``LayoutResolution.duplicates``. ROIs whose name is not
    a Barnes name of this layout are ignored (the user's own ROIs may coexist).
    ``quadrante_alvo`` is optional.
    """
    by_name: dict[str, ROI] = {}
    duplicates: list[str] = []
    for roi in rois:
        if parse_barnes_roi_name(roi.name, n_holes) is None:
            continue
        if roi.name in by_name:
            logger.warning("barnes.layout.duplicate_roi", roi=roi.name)
            if roi.name not in duplicates:
                duplicates.append(roi.name)
            continue
        by_name[roi.name] = roi
    repeated = tuple(duplicates)

    holes: list[LayoutHole] = []
    missing: list[str] = []
    for name in expected_roi_names(n_holes):
        parsed = parse_barnes_roi_name(name, n_holes)
        if parsed is None or parsed.kind is not BarnesRoiKind.HOLE or parsed.offset is None:
            continue
        hole_roi = by_name.get(name)
        if hole_roi is None or not _usable(hole_roi):
            missing.append(name)
            continue
        holes.append(
            LayoutHole(offset=parsed.offset, roi=hole_roi, area_px=float(hole_roi.geometry.area))
        )
    if missing:
        logger.warning("barnes.layout.missing_rois", missing=missing, n_holes=n_holes)
        return LayoutResolution(layout=None, missing=tuple(missing), duplicates=repeated)

    holes.sort(key=lambda hole: hole.offset % n_holes)
    centers = np.array(
        [(hole.roi.geometry.centroid.x, hole.roi.geometry.centroid.y) for hole in holes],
        dtype=float,
    )
    ring = _fit_ellipse(centers)
    if ring is None:
        logger.warning("barnes.layout.degenerate_ring", n_holes=n_holes)
        return LayoutResolution(layout=None, duplicates=repeated)

    arena = np.asarray(arena_polygon_px, dtype=float).reshape(-1, 2)
    table = _fit_ellipse(arena) if len(arena) >= _MIN_FIT_POINTS else None

    contract_holes = tuple(
        BarnesHole(
            offset=circular_offset(hole.offset % n_holes, 0, n_holes),
            abs_index=hole.offset % n_holes,
            center_px=(float(cx), float(cy)),
            radius_px=math.sqrt(hole.area_px / math.pi),
        )
        for hole, (cx, cy) in zip(holes, centers, strict=True)
    )
    layout = BarnesLayout(
        n_holes=n_holes,
        target_abs_index=0,
        table=table if table is not None else ring,
        ring=ring,
        holes=contract_holes,
        source="reconstructed",
    )
    quadrant = by_name.get(QUADRANT_ROI)
    if quadrant is not None and not _usable(quadrant):
        logger.warning("barnes.layout.empty_quadrant", roi=QUADRANT_ROI)
        quadrant = None
    return LayoutResolution(
        layout=ResolvedLayout(layout=layout, holes=tuple(holes), quadrant=quadrant),
        duplicates=repeated,
    )
