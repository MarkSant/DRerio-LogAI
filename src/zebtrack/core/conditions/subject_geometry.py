"""Subject geometry for the analysis-window engine (ADR-011, Barnes v8.1 #633).

Two numbers per processed frame let the engine tell a rat that only TOUCHES the
escape hole (encounter) apart from one that is going IN (entry, four paws in):

- ``area_px`` — the area of the subject's bounding box. A rat climbing into the
  hole stays partly visible, much smaller than its usual size.
- ``cover`` — for each ROI the box overlaps, ``area(box ∩ roi) / area(box)``: the
  fraction of the VISIBLE subject that lies over that ROI.

Both observation builders — the offline one
(:func:`zebtrack.analysis.window_observations.build_window_observations`, from the
trajectory) and the live one (:class:`zebtrack.core.recording.condition_runtime.ConditionRuntime`,
from the detector) — go through this module, from the same detection that decides
``subject_rois``. There is no second implementation of the geometry: the live
:func:`observe_subject` and the offline :func:`observe_subjects` share
:func:`_cover_columns`, so online and offline cannot disagree on the same box.

The ROIs are used as stored: a Barnes ``toca`` is already the DILATED hole disk
(``hole_roi_dilation``, drawn by the arena assistant), and the occupancy rule's
own buffer (``centroid_in_on_buffered_roi``) is a rule about centroids, not about
how much of the animal is over the hole.

Pure: numpy and shapely only. ``core`` must never import ``analysis``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import shapely
import structlog
from shapely.geometry.base import BaseGeometry

__all__ = [
    "Box",
    "SubjectGeometry",
    "observe_subject",
    "observe_subjects",
    "pick_subject_bbox",
    "prepare_rois",
]

log = structlog.get_logger()

#: ``(x1, y1, x2, y2)`` in the pixel space of the ROIs.
Box = tuple[float, float, float, float]

#: Overlaps below this fraction are floating-point noise of an edge contact.
_MIN_COVER = 1e-9


@dataclass(frozen=True, slots=True)
class SubjectGeometry:
    """Geometry of the subject on one frame.

    Attributes:
        area_px: Area (px²) of the chosen subject box; ``None`` when there was no
            usable subject detection on the frame.
        cover: ROI name -> fraction of the box over that ROI, in ``(0, 1]``. A
            ROI the box does not overlap is absent (reads as ``0.0``).
    """

    area_px: float | None
    cover: Mapping[str, float] = field(default_factory=dict)


#: The geometry of a frame without a subject.
NO_SUBJECT = SubjectGeometry(area_px=None, cover={})


def _normalised_box(values: Sequence[float]) -> Box | None:
    """``(x1, y1, x2, y2)`` with ``x1 < x2`` and ``y1 < y2``; ``None`` when unusable.

    A box with a non-finite corner or no area cannot be divided into: it is not
    a subject the geometry can describe, so it never becomes a tiny "entry".
    """
    try:
        x1, y1, x2, y2 = (float(v) for v in values[:4])
    except (TypeError, ValueError, IndexError):
        return None
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def pick_subject_bbox(boxes: Sequence[Sequence[float]]) -> Box | None:
    """The subject box of a frame: highest confidence, then larger area.

    Args:
        boxes: ``(x1, y1, x2, y2, confidence)`` per subject detection (extra
            items, such as a track id, are ignored). A missing or non-numeric
            confidence counts as ``0.0``. Boxes without area or with a
            non-finite corner are skipped.

    Returns:
        The chosen ``(x1, y1, x2, y2)``, normalised; ``None`` when no box is usable.
    """
    best: Box | None = None
    best_key: tuple[float, float] | None = None
    for item in boxes:
        box = _normalised_box(item)
        if box is None:
            continue
        try:
            confidence = float(item[4]) if len(item) > 4 else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            confidence = 0.0
        key = (confidence, (box[2] - box[0]) * (box[3] - box[1]))
        if best_key is None or key > best_key:
            best, best_key = box, key
    return best


def prepare_rois(rois: Sequence[tuple[str, BaseGeometry]]) -> tuple[tuple[str, BaseGeometry], ...]:
    """Valid, non-empty, prepared copies of ``rois`` (invalid ones repaired once).

    Callers that observe many frames against the same ROIs call this once;
    :func:`observe_subject` and :func:`observe_subjects` accept raw ROIs too.
    """
    prepared: list[tuple[str, BaseGeometry]] = []
    for name, geometry in rois:
        if geometry is None or geometry.is_empty:
            continue
        shape = geometry if geometry.is_valid else geometry.buffer(0)
        if shape.is_empty or shape.area <= 0:
            continue
        shapely.prepare(shape)
        prepared.append((str(name), shape))
    return tuple(prepared)


def _cover_columns(
    boxes: np.ndarray, rois: Sequence[tuple[str, BaseGeometry]]
) -> list[tuple[str, np.ndarray]]:
    """``(roi name, cover of every box)`` — the ONE implementation of the geometry.

    ``boxes`` is an ``(n, 4)`` array of normalised boxes with positive area. One
    ROI at a time, so memory stays ``O(n)`` however many ROIs the arena has.
    """
    polygons = shapely.box(boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3])
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    columns: list[tuple[str, np.ndarray]] = []
    for name, geometry in rois:
        overlap = shapely.area(shapely.intersection(polygons, geometry))
        columns.append((name, np.clip(overlap / areas, 0.0, 1.0)))
    return columns


def _geometry_rows(
    boxes: Sequence[Box | None],
    rois: Sequence[tuple[str, BaseGeometry]],
    *,
    prepared: bool = False,
) -> list[SubjectGeometry]:
    usable = [index for index, box in enumerate(boxes) if box is not None]
    result = [NO_SUBJECT] * len(boxes)
    if not usable:
        return result
    array = np.asarray([boxes[index] for index in usable], dtype=np.float64)
    areas = (array[:, 2] - array[:, 0]) * (array[:, 3] - array[:, 1])
    shapes = rois if prepared else prepare_rois(rois)
    columns = _cover_columns(array, shapes) if shapes else []
    for row, index in enumerate(usable):
        cover: dict[str, float] = {}
        for name, values in columns:
            fraction = float(values[row])
            if fraction > _MIN_COVER:
                cover[name] = max(fraction, cover.get(name, 0.0))
        result[index] = SubjectGeometry(area_px=float(areas[row]), cover=cover)
    return result


def observe_subject(
    bbox: Sequence[float] | None,
    rois: Sequence[tuple[str, BaseGeometry]],
    *,
    prepared: bool = False,
) -> SubjectGeometry:
    """Area and per-ROI cover of one frame's subject box (live, one frame at a time).

    Args:
        bbox: ``(x1, y1, x2, y2)`` of the subject (see :func:`pick_subject_bbox`),
            or ``None`` when no subject was detected.
        rois: ``(name, shapely geometry)`` in the same pixel space as ``bbox``.
            Two ROIs with the same name keep the larger cover.
        prepared: ``rois`` already went through :func:`prepare_rois` (the live
            runtime prepares them once per zone set, not once per frame).
    """
    box = None if bbox is None else _normalised_box(bbox)
    return _geometry_rows([box], rois, prepared=prepared)[0]


def observe_subjects(
    bboxes: Sequence[Sequence[float] | None], rois: Sequence[tuple[str, BaseGeometry]]
) -> list[SubjectGeometry]:
    """:func:`observe_subject` for a whole recording at once (offline builder).

    Vectorised over frames; the result has one entry per item of ``bboxes``.
    """
    normalised = [None if box is None else _normalised_box(box) for box in bboxes]
    rows = _geometry_rows(normalised, rois)
    log.debug(
        "conditions.subject_geometry.observed",
        frames=len(rows),
        with_subject=sum(1 for row in rows if row.area_px is not None),
        rois=len(rois),
    )
    return rows
