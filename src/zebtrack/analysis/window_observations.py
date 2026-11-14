"""Per-frame observations the condition engine reads, rebuilt from what was recorded.

The analysis window (ADR-011) is evaluated by :mod:`zebtrack.core.conditions`
over a stream of :class:`~zebtrack.core.conditions.FrameObservation`. Live, the
pipeline builds them as it goes; for the analysis they are rebuilt here from the
files a recording leaves behind:

- the ``3c_Objetos_`` sidecar (ADR-010) gives one observation per HEARTBEAT
  (``class_id == -1``): its ``frame`` and event clock ``t_event_s``, and the
  confidences of every subject/context detection of that frame by normalised
  class name. The heartbeat is what tells "nothing was seen" apart from "this
  frame was never processed", which absence conditions depend on;
- the trajectory gives the ROIs the subject occupies, decided by the SAME rule
  the report uses (:func:`resolve_roi_rule` + :class:`ROIAnalyzer`, debounce
  included), so a window that says "rat inside ``toca``" and the report's
  latency to ``toca`` cannot disagree on when that happened;
- the artifact's ``external_events`` (recorded live) are delivered with the
  first observation at or after their instant.

Without a ``3c`` (a 7.2 project, or the sidecar switched off) the stream is
rebuilt from the trajectory alone: subject presence and ROIs on the trajectory's
own frame grid, with a warning. A condition that needs a class the trajectory
cannot see (a context class, or a class name that is not known to be the subject)
is then reported by :func:`missing_inputs` instead of being evaluated as "absent".
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import structlog

from zebtrack.analysis.time_base import resolve_time_base
from zebtrack.analysis.track_significance import (
    DEFAULT_MIN_TRACK_DURATION_S,
    TrackScreening,
    screen_subjects,
)
from zebtrack.core.conditions.evaluator import ExternalEvent, FrameObservation
from zebtrack.core.conditions.model import (
    ClassPresence,
    RoiEdge,
    RoiInside,
    WindowSpec,
    _normalize_class_name,
    iter_nodes,
)
from zebtrack.i18n import _
from zebtrack.io.object_sidecar import CLOCK_PTS, HEARTBEAT_CLASS_ID

if TYPE_CHECKING:
    from zebtrack.analysis.roi import ROI
    from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig

__all__ = [
    "TRAJECTORY_SUBJECT_CLASS",
    "WindowObservations",
    "build_window_observations",
    "missing_inputs",
    "no_object_sidecar_warning",
    "role_names_from_metadata",
    "screen_window_subjects",
    "subject_rois_by_frame",
]

log = structlog.get_logger()

#: Class name given to the trajectory's subject when the stream is rebuilt
#: without a ``3c`` and the subject's real class name is not known. It is
#: mapped to the ``subject`` role, so ``{"role": "subject"}`` conditions work.
#: Already in normalised form (the engine normalises role names).
TRAJECTORY_SUBJECT_CLASS = "__trajectory_subject__"

#: Engine roles a condition can target (``ClassTarget.role``).
_ROLES = ("subject", "context")


@dataclass(frozen=True)
class WindowObservations:
    """What :func:`build_window_observations` produced.

    Attributes:
        observations: One per processed frame, in frame order.
        role_names: ``{"subject": {...}, "context": {...}}`` for the engine.
        has_objects: The stream came from a ``3c`` sidecar (heartbeats).
        clock: Clock of ``t_s`` (``"pts"`` or ``"capture_perf"``).
        subject_names: Normalised class names known to be the subject.
        warnings: User-facing warnings, already translated.
    """

    observations: tuple[FrameObservation, ...]
    role_names: Mapping[str, frozenset[str]]
    has_objects: bool
    clock: str
    subject_names: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = field(default_factory=tuple)


def no_object_sidecar_warning() -> str:
    """Report warning for a window rebuilt without the ``3c`` sidecar."""
    return _(
        "No object sidecar (3c_Objetos_) was found for this recording: the analysis "
        "window was evaluated from the trajectory alone (subject presence and ROIs). "
        "Frames before the first or after the last detection of the subject cannot "
        "be observed."
    )


def role_names_from_metadata(class_roles: Mapping[str, str] | None) -> dict[str, frozenset[str]]:
    """``{normalised name: role}`` of the ``3c`` metadata -> engine role map."""
    grouped: dict[str, set[str]] = {role: set() for role in _ROLES}
    for name, role in (class_roles or {}).items():
        if role in grouped:
            grouped[role].add(_normalize_class_name(str(name)))
    return {role: frozenset(names) for role, names in grouped.items()}


def _frame_times(trajectory_df: pd.DataFrame) -> pd.DataFrame:
    """``frame`` -> first ``timestamp`` of that frame (seconds), sorted by frame."""
    frames = pd.to_numeric(trajectory_df["frame"], errors="coerce")
    times = pd.to_numeric(trajectory_df["timestamp"], errors="coerce")
    table = pd.DataFrame({"frame": frames, "t_s": times}).dropna()
    table["frame"] = table["frame"].astype(np.int64)
    return table.groupby("frame", sort=True)["t_s"].first().reset_index()


def screen_window_subjects(
    trajectory_df: pd.DataFrame | None,
    *,
    min_track_duration_s: float = DEFAULT_MIN_TRACK_DURATION_S,
) -> TrackScreening | None:
    """The report's subject screening, applied to the trajectory the window reads.

    ``AnalysisService.run_full_analysis`` drops, before anything counts
    animals, the rows without a ``track_id`` next to identified tracks (#671)
    and the tracks shorter than ``min_track_duration_s`` (#649). The window
    reads the SAME trajectory file, so it runs the same
    :func:`~zebtrack.analysis.track_significance.screen_subjects`: otherwise a
    one-row glitch inside a ROI starts a window the report then measures
    without that row. ``None`` when there is no trajectory.
    """
    if trajectory_df is None or trajectory_df.empty:
        return None
    timestamps = (
        pd.to_numeric(trajectory_df["timestamp"], errors="coerce")
        if "timestamp" in trajectory_df.columns
        else None
    )
    median_dt = (
        resolve_time_base(trajectory_df.assign(timestamp=timestamps)).median_dt
        if timestamps is not None and timestamps.notna().any()
        else None
    )
    return screen_subjects(trajectory_df, min_duration_s=min_track_duration_s, median_dt=median_dt)


def subject_rois_by_frame(
    trajectory_df: pd.DataFrame | None,
    rois: Sequence[ROI],
    roi_rule: RoiRuleConfig | None,
    *,
    pixelcm: tuple[float, float] = (1.0, 1.0),
    mask_source: Any = None,
    min_track_duration_s: float = DEFAULT_MIN_TRACK_DURATION_S,
) -> dict[int, frozenset[str]]:
    """ROIs the subject occupies on each trajectory frame, by the report's rule.

    Multi-animal: a ROI counts as occupied while ANY subject is inside
    (``any_track``, the report's group semantics). Frames without a subject row
    are absent from the result (the subject is in no ROI there). Only the
    subjects the report analyses count (:func:`screen_window_subjects`).
    """
    screening = screen_window_subjects(trajectory_df, min_track_duration_s=min_track_duration_s)
    if screening is None:
        return {}
    return _rois_by_frame(screening.trajectory, rois, roi_rule, pixelcm, mask_source)


def _rois_by_frame(
    trajectory_df: pd.DataFrame,
    rois: Sequence[ROI],
    roi_rule: RoiRuleConfig | None,
    pixelcm: tuple[float, float],
    mask_source: Any,
) -> dict[int, frozenset[str]]:
    """:func:`subject_rois_by_frame` on a trajectory already screened."""
    if trajectory_df.empty or not rois:
        return {}
    if "frame" not in trajectory_df.columns or "timestamp" not in trajectory_df.columns:
        return {}

    from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
    from zebtrack.analysis.roi import ROIAnalyzer
    from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

    rule = roi_rule if roi_rule is not None else resolve_roi_rule(None, None)
    columns = [
        c
        for c in (
            "timestamp",
            "frame",
            "track_id",
            "x_center_px",
            "y_center_px",
            "x1",
            "y1",
            "x2",
            "y2",
        )
        if c in trajectory_df.columns
    ]
    subset = trajectory_df[columns].copy()
    subset["timestamp"] = pd.to_numeric(subset["timestamp"], errors="coerce")
    subset = subset.dropna(subset=["timestamp"])
    if subset.empty:
        return {}
    b_analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=subset.copy(),
        pixelcm_x=float(pixelcm[0]) or 1.0,
        pixelcm_y=float(pixelcm[1]) or 1.0,
        video_height_px=0,
        arena_polygon_px=[],
        window_length=1,
        polyorder=0,
    )
    analyzer = ROIAnalyzer.from_rule(b_analyzer, list(rois), rule, mask_source=mask_source)
    timeline = analyzer.presence_timeline()

    # Same float -> ns conversion the behavioural analyser applied to its index.
    table = _frame_times(subset)
    keys = pd.to_timedelta(table["t_s"], unit="s").to_numpy(dtype="timedelta64[ns]")
    frame_of = {
        int(ns): int(frame) for ns, frame in zip(keys.astype(np.int64), table["frame"], strict=True)
    }
    clock_ns = pd.TimedeltaIndex(timeline.index).asi8
    values = timeline.to_numpy(dtype=bool)
    names = list(timeline.columns)
    result: dict[int, frozenset[str]] = {}
    for ns, row in zip(clock_ns, values, strict=True):
        frame = frame_of.get(int(ns))
        if frame is None:
            continue
        result[frame] = frozenset(name for name, inside in zip(names, row, strict=True) if inside)
    return result


def _filter_aquarium(objects_df: pd.DataFrame, aquarium_id: int | None) -> pd.DataFrame:
    """Rows of one aquarium; a null ``aquarium_id`` applies to every aquarium."""
    if aquarium_id is None or "aquarium_id" not in objects_df.columns:
        return objects_df
    owner = objects_df["aquarium_id"]
    # Kleene logic: a null owner is True | NA = True, so no NA survives.
    keep = owner.isna() | (owner == int(aquarium_id))
    return objects_df[keep.to_numpy(dtype=bool)]


def _classes_by_frame(detections: pd.DataFrame) -> dict[int, dict[str, tuple[float, ...]]]:
    """``frame -> {normalised class name: confidences}`` of the detection rows."""
    grouped: dict[int, dict[str, list[float]]] = {}
    names = detections["class_name"].astype("string").fillna("")
    confidences = pd.to_numeric(detections["confidence"], errors="coerce").fillna(0.0)
    for frame, name, confidence in zip(
        detections["frame"].astype(np.int64), names, confidences, strict=True
    ):
        normalised = _normalize_class_name(str(name))
        if not normalised:
            continue
        grouped.setdefault(int(frame), {}).setdefault(normalised, []).append(float(confidence))
    return {
        frame: {name: tuple(values) for name, values in classes.items()}
        for frame, classes in grouped.items()
    }


def _attach_external(
    frames: Sequence[int], times: Sequence[float], events: Iterable[ExternalEvent]
) -> dict[int, tuple[ExternalEvent, ...]]:
    """Deliver every event with the first observation at or after its instant."""
    attached: dict[int, list[ExternalEvent]] = {}
    clock = np.asarray(times, dtype=float)
    for event in sorted(events, key=lambda e: e.t_s):
        position = int(np.searchsorted(clock, float(event.t_s) - 1e-9, side="left"))
        if position >= len(frames):
            log.warning(
                "window_observations.external_after_stream",
                t_s=event.t_s,
                source=event.source,
                code=event.code,
            )
            continue
        attached.setdefault(int(frames[position]), []).append(event)
    return {frame: tuple(items) for frame, items in attached.items()}


def _known_subject_names(
    role_names: Mapping[str, frozenset[str]], subject_names: Iterable[str]
) -> frozenset[str]:
    extra = {_normalize_class_name(str(n)) for n in subject_names if str(n).strip()}
    return frozenset(role_names.get("subject", frozenset())) | frozenset(extra)


def build_window_observations(
    trajectory_df: pd.DataFrame | None,
    *,
    objects_df: pd.DataFrame | None = None,
    rois: Sequence[ROI] = (),
    roi_rule: RoiRuleConfig | None = None,
    external_events: Iterable[ExternalEvent] = (),
    aquarium_id: int | None = None,
    subject_names: Iterable[str] = (),
    clock: str | None = None,
    pixelcm: tuple[float, float] = (1.0, 1.0),
    mask_source: Any = None,
    min_track_duration_s: float = DEFAULT_MIN_TRACK_DURATION_S,
) -> WindowObservations:
    """Rebuild the observation stream of one recording (one aquarium).

    Args:
        trajectory_df: The trajectory (``timestamp`` in seconds on the event
            clock — re-timed already for a live session — plus ``frame`` and
            the bbox/centre columns), in the same pixel space as ``rois``.
        objects_df: The ``3c_Objetos_`` sidecar as returned by
            :func:`zebtrack.io.object_sidecar.read_object_sidecar`, or ``None``.
        rois: ROIs for ``RoiInside``/``RoiEdge``.
        roi_rule: The report's resolved ROI rule (default rule when ``None``).
        external_events: Arduino/manual events recorded for the session.
        aquarium_id: Keep only this aquarium's sidecar rows (null rows apply to
            every aquarium) and stamp the observations with it.
        subject_names: Class names known to be the subject (the project's role
            map). Used only without a ``3c``, whose metadata already says it.
        clock: Clock of the trajectory when there is no ``3c``.
        pixelcm: Calibration, for the buffered-centroid ROI rule only.
        mask_source: ``3b_Mascaras_`` sidecar, for the ``seg_overlap`` rule.
        min_track_duration_s: The report's ``min_track_duration_s``, so the
            window screens the same short tracks (``<= 0`` disables it).
    """
    warnings: list[str] = []
    # One screening for the ROI presence AND the trajectory-only stream: the
    # window sees the subjects the report analyses (#671).
    screening = screen_window_subjects(trajectory_df, min_track_duration_s=min_track_duration_s)
    if screening is not None:
        trajectory_df = screening.trajectory
        warnings.extend(screening.warnings)
    rois_by_frame = (
        {}
        if trajectory_df is None
        else _rois_by_frame(trajectory_df, rois, roi_rule, pixelcm, mask_source)
    )

    if objects_df is not None and not objects_df.empty:
        metadata = objects_df.attrs.get("objects_metadata")
        role_names = role_names_from_metadata(getattr(metadata, "class_roles", None))
        objects = _filter_aquarium(objects_df, aquarium_id)
        class_ids = pd.to_numeric(objects["class_id"], errors="coerce")
        heartbeats = objects[(class_ids == HEARTBEAT_CLASS_ID).to_numpy(dtype=bool)]
        detections = objects[(class_ids != HEARTBEAT_CLASS_ID).to_numpy(dtype=bool)]
        beats = (
            pd.DataFrame(
                {
                    "frame": heartbeats["frame"].astype(np.int64),
                    "t_s": pd.to_numeric(heartbeats["t_event_s"], errors="coerce"),
                }
            )
            .dropna()
            .drop_duplicates(subset="frame")
            .sort_values("frame", kind="stable")
        )
        frames = beats["frame"].tolist()
        times = beats["t_s"].astype(float).tolist()
        classes = _classes_by_frame(detections)
        has_objects = True
        stream_clock = str(getattr(metadata, "clock", "") or clock or CLOCK_PTS)
        known_subjects = _known_subject_names(role_names, ())
    else:
        role_names, frames, times, classes, known_subjects = _from_trajectory_only(
            trajectory_df, subject_names
        )
        has_objects = False
        stream_clock = clock or CLOCK_PTS
        warnings.append(no_object_sidecar_warning())

    external = _attach_external(frames, times, external_events)
    observations = tuple(
        FrameObservation(
            frame=int(frame),
            t_s=float(t_s),
            classes=classes.get(int(frame), {}),
            subject_rois=rois_by_frame.get(int(frame), frozenset()),
            external=external.get(int(frame), ()),
            aquarium_id=aquarium_id,
        )
        for frame, t_s in zip(frames, times, strict=True)
        if math.isfinite(float(t_s))
    )
    log.info(
        "window_observations.built",
        observations=len(observations),
        has_objects=has_objects,
        aquarium_id=aquarium_id,
        clock=stream_clock,
    )
    return WindowObservations(
        observations=observations,
        role_names=role_names,
        has_objects=has_objects,
        clock=stream_clock,
        subject_names=known_subjects,
        warnings=tuple(warnings),
    )


def _from_trajectory_only(
    trajectory_df: pd.DataFrame | None, subject_names: Iterable[str]
) -> tuple[
    dict[str, frozenset[str]],
    list[int],
    list[float],
    dict[int, dict[str, tuple[float, ...]]],
    frozenset[str],
]:
    """Stream rebuilt from the trajectory: a frame grid with subject presence.

    The grid runs from the first to the last trajectory frame at the modal
    frame step (the processing cadence); a grid frame without a subject row is
    an observation WITHOUT the subject, dated by linear interpolation of the
    trajectory clock. Beyond the trajectory's ends nothing can be observed.
    """
    known = frozenset(_normalize_class_name(str(n)) for n in subject_names if str(n).strip())
    subject_key = next(iter(known)) if len(known) == 1 else TRAJECTORY_SUBJECT_CLASS
    role_names = {"subject": frozenset({subject_key}), "context": frozenset()}
    if trajectory_df is None or trajectory_df.empty or "frame" not in trajectory_df.columns:
        return role_names, [], [], {}, known

    table = _frame_times(trajectory_df)
    if table.empty:
        return role_names, [], [], {}, known
    known_frames = table["frame"].to_numpy(dtype=np.int64)
    known_times = table["t_s"].to_numpy(dtype=float)
    steps = np.diff(known_frames)
    step = int(pd.Series(steps).mode().iloc[0]) if steps.size else 1
    step = max(step, 1)
    grid = np.arange(int(known_frames[0]), int(known_frames[-1]) + 1, step, dtype=np.int64)
    grid = np.union1d(grid, known_frames)
    grid_times = np.interp(grid, known_frames, known_times)

    confidences: dict[int, list[float]] = {}
    conf_column = (
        pd.to_numeric(trajectory_df["confidence"], errors="coerce").fillna(1.0)
        if "confidence" in trajectory_df.columns
        else pd.Series(1.0, index=trajectory_df.index)
    )
    frame_column = pd.to_numeric(trajectory_df["frame"], errors="coerce")
    for frame, confidence in zip(frame_column, conf_column, strict=True):
        if pd.isna(frame):
            continue
        confidences.setdefault(int(frame), []).append(float(confidence))
    classes = {frame: {subject_key: tuple(values)} for frame, values in confidences.items()}
    return role_names, grid.tolist(), grid_times.astype(float).tolist(), classes, known


def missing_inputs(
    spec: WindowSpec,
    *,
    has_objects: bool,
    subject_names: Iterable[str],
    roi_names: Iterable[str],
) -> list[str]:
    """What the spec needs that the recording cannot provide (empty = evaluable).

    Without a ``3c`` only the subject is visible, so a condition on a context
    class (by role, or by a name not known to be the subject) cannot be told
    apart from "absent"; evaluating it would fabricate a START. A ROI the
    project does not define is missing in any case.
    """
    known_subjects = {_normalize_class_name(str(n)) for n in subject_names}
    known_rois = set(roi_names)
    missing: list[str] = []
    for root in (spec.start, spec.stop):
        if root is None:
            continue
        for node in iter_nodes(root):
            if isinstance(node, ClassPresence) and not has_objects:
                target = node.target
                if target.role == "context":
                    missing.append("role:context")
                elif target.class_name is not None and target.class_name not in known_subjects:
                    missing.append(f"class:{target.class_name}")
            elif isinstance(node, RoiInside | RoiEdge) and node.roi not in known_rois:
                missing.append(f"roi:{node.roi}")
    return sorted(set(missing))
