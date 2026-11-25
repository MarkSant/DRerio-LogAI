"""Barnes-maze table geometry: table ellipse, hole ring, snapping and ROIs (#633).

Pure: numpy + OpenCV, no Tk. Everything is in the RAW pixels of the frame the
table was drawn on (``docs/reference/COORDINATE_SYSTEMS.md``); nothing here knows
about canvases or scaling.

The pipeline the arena assistant runs:

1. **Table ellipse** — from the arena detection's outline (:func:`ellipse_from_polygon`)
   or from at least five clicks on the rim (:func:`ellipse_from_points`).
2. **Hole ring** — the click on the escape hole fixes the ring's size and phase in
   the table ellipse's unit-circle frame (:func:`ring_from_click`). ``n_holes``
   holes are placed every ``360 / n_holes`` degrees of the ellipse's PARAMETRIC
   angle: an affine view of a circle with equally spaced holes is an ellipse with
   holes equally spaced in that angle.
3. **Snapping** — on a background where the rat and the experimenter vanished
   (:func:`read_background`, median of ~30 frames), each hole is snapped to the
   dark blob nearest its prediction (:func:`snap_hole`). The ring is then refitted
   through the snapped centres (corrects the residual perspective) and the holes
   are placed and snapped again (:func:`snap_layout`). A hole that is not found
   keeps its prediction.
4. **ROIs** — :func:`build_barnes_rois` turns a :class:`BarnesLayout` into the
   contract's polygons, in ``expected_roi_names`` order (CONTRACTS §3.1).

Hole indexing. ``k`` is the clockwise ordinal from the target (``k = 0`` is the
escape hole); ``abs_index`` is the layout's absolute index, whose origin is the
hole with the smallest screen angle (measured clockwise from "pointing right")
around the ring centre. A fixed origin keeps ``abs_index`` stable across days
when only the escape hole moves.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import structlog

from zebtrack.analysis.protocols.barnes.contract import (
    QUADRANT_ROI,
    BarnesEllipse,
    BarnesHole,
    BarnesLayout,
    BarnesParams,
    LayoutSource,
    circular_offset,
    expected_roi_names,
    hole_roi_name,
)
from zebtrack.core.exceptions import ZebTrackError

__all__ = [
    "ARENA_VERTICES",
    "HOLE_ROI_VERTICES",
    "QUADRANT_MAX_STEP_DEG",
    "BarnesGeometryError",
    "HoleSnap",
    "LayoutQuality",
    "RingModel",
    "assemble_layout",
    "build_barnes_rois",
    "ellipse_from_points",
    "ellipse_from_polygon",
    "ellipse_param",
    "ellipse_point",
    "ellipse_polygon",
    "hole_roi_radii",
    "layout_from_click",
    "layout_quality",
    "predict_hole_centers",
    "read_background",
    "relayout",
    "ring_from_click",
    "ring_model_of_layout",
    "snap_hole",
    "snap_layout",
]

log = structlog.get_logger()

#: Vertices of the arena polygon (the table ellipse). CONTRACTS §3.1.
ARENA_VERTICES = 64
#: Vertices of each hole ROI circle. CONTRACTS §3.1.
HOLE_ROI_VERTICES = 32
#: Upper bound of the angular step between two vertices of ``quadrante_alvo``'s
#: rim arc. CONTRACTS §3.1 asks for "at least one vertex per 3°".
QUADRANT_MAX_STEP_DEG = 3.0
#: Cap of a hole ROI radius, as a fraction of the hole's smallest adjacent spacing.
#: Below 0.5 so two neighbouring hole ROIs can never overlap. CONTRACTS §3.1.
HOLE_ROI_SPACING_CAP = 0.45
#: A hole ROI smaller than this (two hole centres almost on top of each other)
#: means the layout is wrong, not that the hole is tiny.
MIN_HOLE_ROI_RADIUS_PX = 1.0

#: Default background sample size (frames).
DEFAULT_BACKGROUND_SAMPLES = 30
#: Search window of the snap, as a fraction of the hole's adjacent spacing.
SNAP_SEARCH_FRACTION = 0.4
#: Hole radius assumed before any hole was snapped, as a fraction of the spacing.
#: The lab's table (184 cm, holes ~10 cm) is ~0.16; a slightly smaller guess
#: never makes a hole ROI larger than the real hole.
DEFAULT_HOLE_RADIUS_FRACTION = 0.15
#: Smallest gray-level difference between the table surface and a hole for the
#: snap to trust a dark blob (0-255 scale).
MIN_SNAP_CONTRAST = 25.0
#: Accepted blob radius, as fractions of the spacing.
MIN_BLOB_RADIUS_FRACTION = 0.05
MAX_BLOB_RADIUS_FRACTION = 0.35
#: Smallest fill ratio (blob area / its bounding box) of a disk-like blob. A disk
#: fills pi/4 ~ 0.785 of its box; a thin dark seam or a corner of the floor does not.
MIN_BLOB_FILL = 0.5
#: Largest normalised-radius error of a rim point on its fitted ellipse.
MAX_RIM_MISFIT = 0.25
#: Snapped holes needed to refit the ring (``cv2.fitEllipse`` needs five points).
MIN_HOLES_TO_REFIT = 5

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

Point = tuple[float, float]


class BarnesGeometryError(ZebTrackError):
    """The geometry cannot be built from the given input (degenerate or too few points)."""


# ---------------------------------------------------------------------------
# Ellipses
# ---------------------------------------------------------------------------


def _ellipse_from_rotated_rect(rect: Sequence[object]) -> BarnesEllipse:
    """BarnesEllipse of an OpenCV ``RotatedRect`` ``((cx, cy), (w, h), angle)``."""
    center, size, angle_raw = rect
    cx, cy = (float(v) for v in center)  # type: ignore[attr-defined]
    width, height = (float(v) for v in size)  # type: ignore[attr-defined]
    angle = float(angle_raw)  # type: ignore[arg-type]
    a, b = float(width) / 2.0, float(height) / 2.0
    if not (math.isfinite(a) and math.isfinite(b)) or a <= 0.0 or b <= 0.0:
        raise BarnesGeometryError(f"degenerate ellipse: axes {width!r} x {height!r}")
    return BarnesEllipse(center_px=(cx, cy), semi_axes_px=(a, b), angle_deg=angle)


def ellipse_from_points(points: Sequence[Point]) -> BarnesEllipse:
    """Least-squares ellipse through rim points (``cv2.fitEllipse``).

    Raises:
        BarnesGeometryError: fewer than five points, a degenerate fit, or points
            that do not lie on the fitted ellipse (``cv2.fitEllipse`` returns SOME
            ellipse even for collinear points).
    """
    if len(points) < 5:
        raise BarnesGeometryError(f"an ellipse needs at least 5 points, got {len(points)}")
    array = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    if not np.all(np.isfinite(array)):
        raise BarnesGeometryError("rim points must be finite")
    ellipse = _ellipse_from_rotated_rect(cv2.fitEllipse(array))
    misfit = max(abs(ellipse_param(ellipse, (float(x), float(y)))[1] - 1.0) for x, y in points)
    if misfit > MAX_RIM_MISFIT:
        raise BarnesGeometryError(f"the points do not lie on an ellipse (misfit {misfit:.2f})")
    return ellipse


def ellipse_from_polygon(polygon: Sequence[Point]) -> BarnesEllipse:
    """The table ellipse of an arena outline from the auto-detection.

    A detection box (four corners) gives the ellipse INSCRIBED in its minimum-area
    rectangle: a YOLO ``arena`` box is the table's bounding box. A real outline
    (five or more vertices, segmentation) is fitted with ``cv2.fitEllipse``.

    Raises:
        BarnesGeometryError: fewer than four vertices, or a degenerate outline.
    """
    if len(polygon) < 4:
        raise BarnesGeometryError(f"an arena outline needs at least 4 vertices, got {len(polygon)}")
    if len(polygon) == 4:
        array = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
        return _ellipse_from_rotated_rect(cv2.minAreaRect(array))
    return ellipse_from_points(polygon)


def ellipse_point(ellipse: BarnesEllipse, t: float) -> Point:
    """Point of ``ellipse`` at parametric angle ``t`` (radians, clockwise on screen)."""
    cx, cy = ellipse.center_px
    a, b = ellipse.semi_axes_px
    theta = math.radians(ellipse.angle_deg)
    ux, uy = a * math.cos(t), b * math.sin(t)
    return (
        cx + ux * math.cos(theta) - uy * math.sin(theta),
        cy + ux * math.sin(theta) + uy * math.cos(theta),
    )


def ellipse_param(ellipse: BarnesEllipse, point: Point) -> tuple[float, float]:
    """``(t, rho)`` of ``point`` in the ellipse's unit-circle frame.

    ``t`` is the parametric angle (radians, in ``(-pi, pi]``) and ``rho`` the
    normalised radius: ``1`` on the ellipse, ``< 1`` inside.
    """
    cx, cy = ellipse.center_px
    a, b = ellipse.semi_axes_px
    theta = math.radians(ellipse.angle_deg)
    dx, dy = point[0] - cx, point[1] - cy
    u = (dx * math.cos(theta) + dy * math.sin(theta)) / a
    v = (-dx * math.sin(theta) + dy * math.cos(theta)) / b
    return math.atan2(v, u), math.hypot(u, v)


def ellipse_polygon(ellipse: BarnesEllipse, n_vertices: int = ARENA_VERTICES) -> list[Point]:
    """``n_vertices`` points around ``ellipse``, clockwise on screen."""
    if n_vertices < 3:
        raise BarnesGeometryError(f"a polygon needs at least 3 vertices, got {n_vertices}")
    step = 2.0 * math.pi / n_vertices
    return [ellipse_point(ellipse, k * step) for k in range(n_vertices)]


def _scaled(ellipse: BarnesEllipse, factor: float) -> BarnesEllipse:
    a, b = ellipse.semi_axes_px
    return BarnesEllipse(
        center_px=ellipse.center_px,
        semi_axes_px=(a * factor, b * factor),
        angle_deg=ellipse.angle_deg,
    )


def _contains(ellipse: BarnesEllipse, point: Point) -> bool:
    return ellipse_param(ellipse, point)[1] < 1.0


# ---------------------------------------------------------------------------
# Ring model and hole placement
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RingModel:
    """Where the holes are predicted to be.

    Attributes:
        ring: Ellipse through the hole centres.
        phase: Parametric angle (radians) of the escape hole (``k = 0``) on ``ring``.
        n_holes: Holes around the ring; hole ``k`` sits at ``phase + k * step``.
    """

    ring: BarnesEllipse
    phase: float
    n_holes: int

    @property
    def step(self) -> float:
        return 2.0 * math.pi / self.n_holes

    def rotated(self, delta_rad: float) -> RingModel:
        """The same ring with the escape hole moved by ``delta_rad`` (clockwise > 0)."""
        return RingModel(ring=self.ring, phase=self.phase + delta_rad, n_holes=self.n_holes)


def ring_from_click(table: BarnesEllipse, click: Point, n_holes: int) -> RingModel:
    """Ring through the escape-hole click, concentric with the table.

    Raises:
        BarnesGeometryError: the click is outside the table, or on its centre.
    """
    if n_holes < 3:
        raise BarnesGeometryError(f"n_holes must be at least 3, got {n_holes}")
    t, rho = ellipse_param(table, click)
    if rho >= 1.0:
        raise BarnesGeometryError("the escape hole must be inside the table")
    if rho < 0.05:
        raise BarnesGeometryError("the escape hole cannot be the centre of the table")
    return RingModel(ring=_scaled(table, rho), phase=t, n_holes=n_holes)


def predict_hole_centers(model: RingModel) -> list[Point]:
    """Predicted centre of every hole, indexed by ``k`` (0 = escape hole)."""
    return [ellipse_point(model.ring, model.phase + k * model.step) for k in range(model.n_holes)]


def _adjacent_spacings(centers: Sequence[Point]) -> list[float]:
    """Per hole, the distance to its nearer ring neighbour (centres in ring order)."""
    n = len(centers)
    spacings: list[float] = []
    for k in range(n):
        prev_c, here, next_c = centers[k - 1], centers[k], centers[(k + 1) % n]
        spacings.append(
            min(
                math.hypot(here[0] - prev_c[0], here[1] - prev_c[1]),
                math.hypot(here[0] - next_c[0], here[1] - next_c[1]),
            )
        )
    return spacings


# ---------------------------------------------------------------------------
# Background and snapping
# ---------------------------------------------------------------------------


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame.astype(np.uint8, copy=False)
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def read_background(
    source_path: str | Path, n_samples: int = DEFAULT_BACKGROUND_SAMPLES
) -> np.ndarray | None:
    """Grayscale background of a video: the per-pixel median of ``n_samples`` frames.

    The rat and the experimenter move, so the median keeps only the table. An image
    file (the live camera's reference snapshot) is its own background. ``None``
    (logged) when nothing can be read: the caller places the holes unsnapped.
    """
    path = Path(source_path)
    if not path.is_file():
        log.warning("barnes_geometry.background.missing", path=str(path))
        return None
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
        if image is None:
            log.warning("barnes_geometry.background.image_unreadable", path=str(path))
            return None
        return _to_gray(image)

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            log.warning("barnes_geometry.background.video_unreadable", path=str(path))
            return None
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frames: list[np.ndarray] = []
        if frame_count > 0:
            indices = sorted({int(i) for i in np.linspace(0, frame_count - 1, max(1, n_samples))})
            for index in indices:
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if ok and frame is not None:
                    frames.append(_to_gray(frame))
        else:
            # Some containers do not report a frame count: read sequentially.
            while len(frames) < n_samples:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                frames.append(_to_gray(frame))
    finally:
        capture.release()
    if not frames:
        log.warning("barnes_geometry.background.no_frames", path=str(path))
        return None
    stack = np.stack(frames, axis=0)
    background = np.median(stack, axis=0).astype(np.uint8)
    log.info("barnes_geometry.background.ready", path=str(path), frames=len(frames))
    return background


@dataclass(frozen=True, slots=True)
class HoleSnap:
    """A dark blob found near a predicted hole."""

    center_px: Point
    radius_px: float


def snap_hole(
    background: np.ndarray,
    predicted: Point,
    spacing_px: float,
    table: BarnesEllipse | None = None,
) -> HoleSnap | None:
    """The dark, disk-like blob nearest ``predicted``; ``None`` when there is none.

    Searches within ``SNAP_SEARCH_FRACTION * spacing_px`` of the prediction and,
    when ``table`` is given, only inside the table (the floor around the rim is
    dark too). The threshold is local: halfway between the darkest pixels of the
    window and its median (the table surface), so uneven lighting does not matter.
    """
    gray = _to_gray(background)
    height, width = gray.shape[:2]
    radius = SNAP_SEARCH_FRACTION * spacing_px
    if radius < 2.0:
        return None
    px, py = predicted
    x0, x1 = max(0, math.floor(px - radius)), min(width, math.ceil(px + radius) + 1)
    y0, y1 = max(0, math.floor(py - radius)), min(height, math.ceil(py + radius) + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    crop = cv2.GaussianBlur(gray[y0:y1, x0:x1], (3, 3), 0)

    yy, xx = np.mgrid[y0:y1, x0:x1]
    region = (xx - px) ** 2 + (yy - py) ** 2 <= radius**2
    if table is not None:
        cx, cy = table.center_px
        a, b = table.semi_axes_px
        theta = math.radians(table.angle_deg)
        dx, dy = xx - cx, yy - cy
        u = (dx * math.cos(theta) + dy * math.sin(theta)) / a
        v = (-dx * math.sin(theta) + dy * math.cos(theta)) / b
        region &= u**2 + v**2 < 1.0
    if int(region.sum()) < 9:
        return None

    values = crop[region].astype(np.float32)
    surface = float(np.median(values))
    darkest = float(np.percentile(values, 2))
    if surface - darkest < MIN_SNAP_CONTRAST:
        return None
    threshold = darkest + 0.5 * (surface - darkest)
    mask = ((crop.astype(np.float32) < threshold) & region).astype(np.uint8)

    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = math.pi * (MIN_BLOB_RADIUS_FRACTION * spacing_px) ** 2
    max_area = math.pi * (MAX_BLOB_RADIUS_FRACTION * spacing_px) ** 2
    best: HoleSnap | None = None
    best_distance = math.inf
    for label in range(1, count):
        area = float(stats[label, cv2.CC_STAT_AREA])
        box_w = float(stats[label, cv2.CC_STAT_WIDTH])
        box_h = float(stats[label, cv2.CC_STAT_HEIGHT])
        if not min_area <= area <= max_area:
            continue
        if area / max(box_w * box_h, 1.0) < MIN_BLOB_FILL:
            continue
        if max(box_w, box_h) > 2.5 * min(box_w, box_h):
            continue
        center = (float(centroids[label][0]) + x0, float(centroids[label][1]) + y0)
        distance = math.hypot(center[0] - px, center[1] - py)
        if distance < best_distance:
            best_distance = distance
            best = HoleSnap(center_px=center, radius_px=math.sqrt(area / math.pi))
    return best


def _snap_all(
    background: np.ndarray, model: RingModel, table: BarnesEllipse
) -> tuple[list[Point], list[HoleSnap | None]]:
    predicted = predict_hole_centers(model)
    spacings = _adjacent_spacings(predicted)
    snaps = [
        snap_hole(background, center, spacing, table)
        for center, spacing in zip(predicted, spacings, strict=True)
    ]
    # Two predictions cannot claim one blob: each window reaches 0.4 x the
    # spacing, so adjacent windows see different (clipped) pieces of anything
    # straddling them and never return the same centre.
    return predicted, snaps


def _circular_mean(angles: Sequence[float]) -> float:
    return math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles))


def _refit_ring(
    model: RingModel, snaps: Sequence[HoleSnap | None], table: BarnesEllipse
) -> RingModel | None:
    """The ring refitted through the snapped centres; ``None`` when not trustworthy."""
    found = [(k, snap.center_px) for k, snap in enumerate(snaps) if snap is not None]
    if len(found) < MIN_HOLES_TO_REFIT:
        return None
    try:
        ring = ellipse_from_points([center for _k, center in found])
    except BarnesGeometryError:
        return None
    table_a, table_b = table.semi_axes_px
    largest = max(table_a, table_b) * 1.05
    smallest = min(table_a, table_b) * 0.2
    if not _contains(table, ring.center_px):
        return None
    if max(ring.semi_axes_px) > largest or min(ring.semi_axes_px) < smallest:
        return None
    step = model.step
    phase = _circular_mean([ellipse_param(ring, center)[0] - k * step for k, center in found])
    return RingModel(ring=ring, phase=phase, n_holes=model.n_holes)


def snap_layout(
    background: np.ndarray, model: RingModel, table: BarnesEllipse
) -> tuple[RingModel, list[HoleSnap | None]]:
    """Snap every hole, refit the ring through the snapped centres, snap again.

    Returns the refined model (the input one when fewer than five holes snapped or
    the refit is implausible) and, per ``k``, the snap or ``None`` (not found).
    """
    _predicted, snaps = _snap_all(background, model, table)
    refined = _refit_ring(model, snaps, table)
    if refined is None:
        return model, snaps
    _predicted, second = _snap_all(background, refined, table)
    if sum(s is not None for s in second) < sum(s is not None for s in snaps):
        # The refit made things worse (a wrong blob pulled the ring): keep round 1.
        return model, snaps
    return refined, second


# ---------------------------------------------------------------------------
# Layout assembly
# ---------------------------------------------------------------------------


def _abs_origin(centers: Sequence[Point], ring_center: Point) -> int:
    """``k`` of the hole with the smallest clockwise screen angle from "pointing right"."""
    cx, cy = ring_center
    angles = [math.atan2(y - cy, x - cx) % (2.0 * math.pi) for x, y in centers]
    return int(min(range(len(centers)), key=lambda k: angles[k]))


def assemble_layout(
    table: BarnesEllipse,
    model: RingModel,
    snaps: Sequence[HoleSnap | None] | None = None,
    manual: Mapping[int, Point] | None = None,
    *,
    source: LayoutSource | None = None,
) -> BarnesLayout:
    """Build the contract's :class:`BarnesLayout` from a ring model and its snaps.

    Args:
        table: Table ellipse.
        model: Ring model (hole ``k`` predicted at ``phase + k * step``).
        snaps: Per ``k``, the snapped blob or ``None``; ``None`` = no snapping ran.
        manual: Per ``k``, a centre the user dragged the hole to; wins over a snap.
        source: Layout source; derived when ``None`` (``snapped`` when any hole
            snapped, otherwise ``click``).
    """
    n = model.n_holes
    snaps = list(snaps) if snaps is not None else [None] * n
    if len(snaps) != n:
        raise BarnesGeometryError(f"{len(snaps)} snaps for {n} holes")
    manual = dict(manual or {})
    predicted = predict_hole_centers(model)
    spacings = _adjacent_spacings(predicted)
    snapped_radii = [s.radius_px for s in snaps if s is not None]
    default_radius = (
        float(np.median(snapped_radii))
        if snapped_radii
        else DEFAULT_HOLE_RADIUS_FRACTION * min(spacings)
    )

    centers: list[Point] = []
    entries: list[tuple[Point, float, bool, float | None]] = []
    for k in range(n):
        snap = snaps[k]
        if k in manual:
            center = (float(manual[k][0]), float(manual[k][1]))
            radius = snap.radius_px if snap is not None else default_radius
            entries.append((center, radius, False, None))
        elif snap is not None:
            residual = math.hypot(
                snap.center_px[0] - predicted[k][0], snap.center_px[1] - predicted[k][1]
            )
            entries.append((snap.center_px, snap.radius_px, True, residual))
            center = snap.center_px
        else:
            center = predicted[k]
            entries.append((center, default_radius, False, None))
        centers.append(center)

    origin = _abs_origin(predicted, model.ring.center_px)
    target_abs = (-origin) % n
    holes: list[BarnesHole] = []
    for abs_index in range(n):
        k = (abs_index + origin) % n
        center, radius, snapped, hole_residual = entries[k]
        holes.append(
            BarnesHole(
                offset=circular_offset(abs_index, target_abs, n),
                abs_index=abs_index,
                center_px=(round(center[0], 2), round(center[1], 2)),
                radius_px=round(radius, 2),
                snapped=snapped,
                residual_px=None if hole_residual is None else round(hole_residual, 2),
            )
        )
    if source is None:
        source = "snapped" if any(s is not None for s in snaps) else "click"
    return BarnesLayout(
        n_holes=n,
        target_abs_index=target_abs,
        table=table,
        ring=model.ring,
        holes=tuple(holes),
        source=source,
    )


def layout_from_click(
    table: BarnesEllipse,
    click: Point,
    n_holes: int,
    background: np.ndarray | None = None,
) -> tuple[BarnesLayout, RingModel]:
    """Whole pipeline: click on the escape hole → snapped layout.

    Without a background the holes stay at their predictions (``source="click"``).

    Returns:
        ``(layout, model)`` — the model is what the assistant rotates or re-snaps.
    """
    model = ring_from_click(table, click, n_holes)
    if background is None:
        return assemble_layout(table, model), model
    model, snaps = snap_layout(background, model, table)
    return assemble_layout(table, model, snaps), model


def relayout(
    table: BarnesEllipse,
    model: RingModel,
    background: np.ndarray | None,
    manual: Mapping[int, Point] | None = None,
) -> BarnesLayout:
    """Re-place the holes of ``model`` (after a rotation, or on another video).

    Snaps without refitting the ring: the user's rotation must not be undone by a
    refit that pulls the ring back onto the blobs it was moved away from.
    """
    if background is None:
        return assemble_layout(table, model, manual=manual)
    _predicted, snaps = _snap_all(background, model, table)
    return assemble_layout(table, model, snaps, manual)


@dataclass(frozen=True, slots=True)
class LayoutQuality:
    """How well the snapped holes agree with the ring (shown by the assistant).

    Attributes:
        snapped: Holes snapped to a dark blob.
        n_holes: Holes in the layout.
        mean_residual_px: Mean prediction → snap distance (``None``: none snapped).
        max_residual_px: Largest such distance (``None``: none snapped).
        mean_spacing_px: Mean distance between adjacent hole centres.
    """

    snapped: int
    n_holes: int
    mean_residual_px: float | None
    max_residual_px: float | None
    mean_spacing_px: float

    @property
    def suspicious(self) -> bool:
        """``True`` when the layout probably does not match the table.

        Some hole was not found, or the snapped holes sit far (more than 15 % of
        the spacing on average) from where an evenly spaced ring puts them: the
        usual sign of a wrong ``n_holes``.
        """
        if self.snapped < self.n_holes:
            return True
        return (
            self.mean_residual_px is not None
            and self.mean_residual_px > 0.15 * self.mean_spacing_px
        )


def layout_quality(layout: BarnesLayout) -> LayoutQuality:
    """Snap count and residuals of ``layout`` (see :class:`LayoutQuality`)."""
    residuals = [
        hole.residual_px for hole in layout.holes if hole.snapped and hole.residual_px is not None
    ]
    spacings = _adjacent_spacings([hole.center_px for hole in layout.holes])
    return LayoutQuality(
        snapped=sum(1 for hole in layout.holes if hole.snapped),
        n_holes=layout.n_holes,
        mean_residual_px=(sum(residuals) / len(residuals)) if residuals else None,
        max_residual_px=max(residuals) if residuals else None,
        mean_spacing_px=sum(spacings) / len(spacings),
    )


def ring_model_of_layout(layout: BarnesLayout) -> RingModel:
    """The ring model a cached layout was built from (target = ``k = 0``)."""
    target = layout.target
    return RingModel(
        ring=layout.ring,
        phase=ellipse_param(layout.ring, target.center_px)[0],
        n_holes=layout.n_holes,
    )


# ---------------------------------------------------------------------------
# ROIs
# ---------------------------------------------------------------------------


def hole_roi_radii(layout: BarnesLayout, params: BarnesParams) -> dict[int, float]:
    """ROI radius of every hole, by ``abs_index``.

    ``min(radius_px * hole_roi_dilation, 0.45 * nearer adjacent spacing)``: two
    neighbouring ROIs can never overlap, whatever the dilation (CONTRACTS §3.1).
    """
    centers = [hole.center_px for hole in layout.holes]
    spacings = _adjacent_spacings(centers)
    return {
        hole.abs_index: min(
            hole.radius_px * params.hole_roi_dilation, HOLE_ROI_SPACING_CAP * spacing
        )
        for hole, spacing in zip(layout.holes, spacings, strict=True)
    }


def _circle(center: Point, radius: float, n_vertices: int = HOLE_ROI_VERTICES) -> list[Point]:
    step = 2.0 * math.pi / n_vertices
    return [
        (center[0] + radius * math.cos(k * step), center[1] + radius * math.sin(k * step))
        for k in range(n_vertices)
    ]


def _ray_exit(table: BarnesEllipse, origin: Point, angle: float) -> Point:
    """Where the ray from ``origin`` (inside ``table``) at screen ``angle`` leaves it."""
    cx, cy = table.center_px
    a, b = table.semi_axes_px
    theta = math.radians(table.angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    def to_unit(dx: float, dy: float) -> tuple[float, float]:
        return (dx * cos_t + dy * sin_t) / a, (-dx * sin_t + dy * cos_t) / b

    p0 = to_unit(origin[0] - cx, origin[1] - cy)
    d = to_unit(math.cos(angle), math.sin(angle))
    qa = d[0] ** 2 + d[1] ** 2
    qb = 2.0 * (p0[0] * d[0] + p0[1] * d[1])
    qc = p0[0] ** 2 + p0[1] ** 2 - 1.0
    disc = qb * qb - 4.0 * qa * qc
    lam = (-qb + math.sqrt(max(disc, 0.0))) / (2.0 * qa)
    return origin[0] + lam * math.cos(angle), origin[1] + lam * math.sin(angle)


def _quadrant_polygon(layout: BarnesLayout, half_holes: int) -> list[Point]:
    """Sector of the target quadrant (CONTRACTS §3.1).

    Bounded by the rays from the ring centre through the ring points mid-way (in
    the ring's parametric angle) between holes ``±half_holes`` and
    ``±(half_holes + 1)``, closed by the table ellipse.
    """
    ring = layout.ring
    n = layout.n_holes
    by_offset_k: dict[int, BarnesHole] = {}
    for hole in layout.holes:
        k = (hole.abs_index - layout.target_abs_index) % n
        by_offset_k[k] = hole

    def param(k: int) -> float:
        return ellipse_param(ring, by_offset_k[k % n].center_px)[0]

    def midpoint(k_inner: int, k_outer: int) -> float:
        inner, outer = param(k_inner), param(k_outer)
        delta = math.atan2(math.sin(outer - inner), math.cos(outer - inner))
        return inner + delta / 2.0

    t_start = midpoint(-half_holes, -half_holes - 1)
    t_end = midpoint(half_holes, half_holes + 1)
    origin = ring.center_px
    if not _contains(layout.table, origin):
        raise BarnesGeometryError("the hole ring's centre is outside the table")
    start_pt = ellipse_point(ring, t_start)
    end_pt = ellipse_point(ring, t_end)
    angle_start = math.atan2(start_pt[1] - origin[1], start_pt[0] - origin[0])
    angle_end = math.atan2(end_pt[1] - origin[1], end_pt[0] - origin[0])
    span = (angle_end - angle_start) % (2.0 * math.pi)
    if span <= 0.0:
        raise BarnesGeometryError("the target quadrant has no extent")
    steps = max(1, math.ceil(math.degrees(span) / QUADRANT_MAX_STEP_DEG))
    arc = [
        _ray_exit(layout.table, origin, angle_start + span * i / steps) for i in range(steps + 1)
    ]
    return [origin, *arc]


def _rounded(points: Sequence[Point]) -> list[Point]:
    return [(round(float(x), 2), round(float(y), 2)) for x, y in points]


def build_barnes_rois(
    layout: BarnesLayout, params: BarnesParams
) -> tuple[list[Point], list[tuple[str, list[Point]]]]:
    """The arena polygon and every Barnes ROI, in ``expected_roi_names`` order.

    Returns:
        ``(arena, rois)``: ``arena`` is the table ellipse as 64 vertices; ``rois``
        is ``[(name, polygon), ...]`` in the contract's stored order.

    Raises:
        BarnesGeometryError: ``params.n_holes`` differs from the layout's, or the
            quadrant cannot be built (ring centre outside the table).
    """
    if params.n_holes != layout.n_holes:
        raise BarnesGeometryError(
            f"the layout has {layout.n_holes} holes but the project expects {params.n_holes}"
        )
    radii = hole_roi_radii(layout, params)
    collapsed = sorted(index for index, radius in radii.items() if radius < MIN_HOLE_ROI_RADIUS_PX)
    if collapsed:
        raise BarnesGeometryError(
            f"holes {collapsed} (abs_index) overlap their neighbours; check the hole count"
        )
    polygons: dict[str, list[Point]] = {}
    for hole in layout.holes:
        name = hole_roi_name(hole.offset, layout.n_holes)
        polygons[name] = _rounded(_circle(hole.center_px, radii[hole.abs_index]))
    names = expected_roi_names(layout.n_holes)
    polygons[QUADRANT_ROI] = _rounded(_quadrant_polygon(layout, params.quadrant_half_holes))
    arena = _rounded(ellipse_polygon(layout.table, ARENA_VERTICES))
    return arena, [(name, polygons[name]) for name in names]
