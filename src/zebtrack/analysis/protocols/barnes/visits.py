"""Hole visits (nose pokes) of a Barnes trial (ADR-014, CONTRACTS §6 "Visits").

A visit to a hole is measured from the subject bbox of each processed frame:
``cover = area(bbox ∩ hole ROI) / area(hole ROI)``. A visit OPENS after
``visit_enter_frames`` consecutive frames with ``cover >= visit_min_cover`` and
CLOSES after ``visit_exit_frames`` consecutive frames below it, both back-dated to
the first frame of the run. A processed frame without a detection counts as below.
With ``visit_max_speed_cm_s`` set, a visit also needs one covered frame below that
speed (a rat running over a hole is not poking it).

Visits are detected over the WHOLE trajectory (the debounce needs the frames before
START) and only then cut to the trial by :func:`visits_in_trial`. Every geometry is
in the space of the ``ProtocolContext``; timestamps are the trajectory's event clock.

Pure: no Tk, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
import shapely

from zebtrack.analysis.protocols.barnes.contract import BarnesParams
from zebtrack.analysis.protocols.barnes.layout import LayoutHole

__all__ = [
    "HoleVisit",
    "SubjectSamples",
    "detect_hole_visits",
    "path_length_cm",
    "subject_samples",
    "visits_in_trial",
]


@dataclass(frozen=True, slots=True)
class SubjectSamples:
    """One subject detection per processed frame, in time order.

    Attributes:
        t_s: Timestamps (event clock), strictly increasing.
        missing_before: Processed frames WITHOUT a detection between the previous
            sample and this one (``0`` for the first sample).
        x1, y1, x2, y2: The subject bbox.
        cx, cy: The subject centre (``x_center_px``/``y_center_px`` when recorded,
            else the bbox centre).
        speed_cm_s: Speed of the centre (backward difference, forward on the first
            sample of a run); ``NaN`` across a gap longer than the gap threshold or
            on an isolated sample.
    """

    t_s: np.ndarray
    missing_before: np.ndarray
    x1: np.ndarray
    y1: np.ndarray
    x2: np.ndarray
    y2: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    speed_cm_s: np.ndarray

    def __len__(self) -> int:
        return len(self.t_s)


@dataclass(frozen=True, slots=True)
class HoleVisit:
    """One visit to one hole.

    Attributes:
        roi: Name of the hole ROI.
        offset: Offset of the hole from the target.
        t_enter_s: Back-dated start (event clock).
        t_exit_s: Back-dated end; ``None`` while the visit is still open (at the end
            of the recording, or — after :func:`visits_in_trial` — at the trial end).
    """

    roi: str
    offset: int
    t_enter_s: float
    t_exit_s: float | None


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _missing_frames(frames: np.ndarray | None, times: np.ndarray) -> np.ndarray:
    """Processed frames without a detection before each sample.

    From the ``frame`` numbers when every sample has one (the step is their smallest
    positive difference: the analysis interval), else from the timestamps and their
    median positive interval (a variable frame rate jitters the smallest one).
    """
    missing = np.zeros(len(times), dtype=int)
    if len(times) < 2:
        return missing
    by_frame = frames is not None and bool(np.all(np.isfinite(frames)))
    diffs = np.diff(frames if by_frame and frames is not None else times)
    positive = diffs[diffs > 0]
    if len(positive) == 0:
        return missing
    step = float(positive.min() if by_frame else np.median(positive))
    missing[1:] = np.maximum(np.rint(diffs / step).astype(int) - 1, 0)
    return missing


def _speeds(
    t: np.ndarray,
    cx: np.ndarray,
    cy: np.ndarray,
    *,
    pixelcm_x: float,
    pixelcm_y: float,
    gap_threshold_s: float,
) -> np.ndarray:
    speeds = np.full(len(t), np.nan)
    if len(t) < 2 or not (pixelcm_x > 0 and pixelcm_y > 0):
        return speeds
    dt = np.diff(t)
    step_cm = np.hypot(np.diff(cx) / pixelcm_x, np.diff(cy) / pixelcm_y)
    valid = (dt > 0) & (dt <= gap_threshold_s)
    step_speed = np.where(valid, step_cm / np.where(dt > 0, dt, 1.0), np.nan)
    speeds[1:] = step_speed
    first_of_run = np.isnan(speeds[:-1]) & ~np.isnan(step_speed)
    speeds[:-1] = np.where(first_of_run, step_speed, speeds[:-1])
    return speeds


def subject_samples(
    trajectory: pd.DataFrame,
    *,
    pixelcm_x: float,
    pixelcm_y: float,
    gap_threshold_s: float,
) -> SubjectSamples:
    """The subject's samples from a ONE-subject trajectory (as recorded).

    Rows without a finite timestamp or bbox are dropped. Several rows on one
    timestamp (an unidentified trajectory) keep the highest confidence, the larger
    bbox on a tie — the same choice the conditions engine makes per frame.
    """
    columns = ("timestamp", "x1", "y1", "x2", "y2")
    if trajectory.empty or any(column not in trajectory.columns for column in columns):
        empty = np.zeros(0)
        return SubjectSamples(
            empty, np.zeros(0, dtype=int), empty, empty, empty, empty, empty, empty, empty
        )
    frame = pd.DataFrame({column: _numeric(trajectory, column) for column in columns})
    frame["confidence"] = (
        _numeric(trajectory, "confidence") if "confidence" in trajectory.columns else 0.0
    )
    frame["confidence"] = frame["confidence"].fillna(0.0)
    frame["frame"] = _numeric(trajectory, "frame") if "frame" in trajectory.columns else np.nan
    for column in ("x_center_px", "y_center_px"):
        frame[column] = _numeric(trajectory, column) if column in trajectory.columns else np.nan
    frame = frame[np.isfinite(frame[list(columns)].to_numpy()).all(axis=1)]
    frame["area"] = (frame["x2"] - frame["x1"]).abs() * (frame["y2"] - frame["y1"]).abs()
    frame = frame.sort_values(
        ["timestamp", "confidence", "area"], ascending=[True, False, False], kind="mergesort"
    ).drop_duplicates("timestamp", keep="first")

    t = frame["timestamp"].to_numpy(dtype=float)
    x1, y1 = frame["x1"].to_numpy(dtype=float), frame["y1"].to_numpy(dtype=float)
    x2, y2 = frame["x2"].to_numpy(dtype=float), frame["y2"].to_numpy(dtype=float)
    recorded_x = frame["x_center_px"].to_numpy(dtype=float)
    recorded_y = frame["y_center_px"].to_numpy(dtype=float)
    recorded = np.isfinite(recorded_x) & np.isfinite(recorded_y)
    cx = np.where(recorded, recorded_x, (x1 + x2) / 2.0)
    cy = np.where(recorded, recorded_y, (y1 + y2) / 2.0)
    frames = frame["frame"].to_numpy(dtype=float)
    return SubjectSamples(
        t_s=t,
        missing_before=_missing_frames(frames, t),
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        cx=cx,
        cy=cy,
        speed_cm_s=_speeds(
            t, cx, cy, pixelcm_x=pixelcm_x, pixelcm_y=pixelcm_y, gap_threshold_s=gap_threshold_s
        ),
    )


def _hole_cover(samples: SubjectSamples, hole: LayoutHole) -> np.ndarray:
    """``area(bbox ∩ hole) / area(hole)`` per sample (0 where they do not overlap)."""
    cover = np.zeros(len(samples))
    min_x, min_y, max_x, max_y = hole.roi.geometry.bounds
    left = np.minimum(samples.x1, samples.x2)
    right = np.maximum(samples.x1, samples.x2)
    top = np.minimum(samples.y1, samples.y2)
    bottom = np.maximum(samples.y1, samples.y2)
    near = (right > min_x) & (left < max_x) & (bottom > min_y) & (top < max_y)
    if near.any():
        boxes = shapely.box(left[near], top[near], right[near], bottom[near])
        cover[near] = shapely.area(shapely.intersection(boxes, hole.roi.geometry)) / hole.area_px
    return cover


class _Debounce:
    """Enter/exit debounce of one hole, frame by frame (back-dated edges)."""

    __slots__ = (
        "_enter",
        "_exit",
        "_inside",
        "_need_slow",
        "_run",
        "_run_slow",
        "_run_t",
        "_slow",
        "_start",
        "visits",
    )

    def __init__(self, enter_frames: int, exit_frames: int, need_slow: bool) -> None:
        self._enter = enter_frames
        self._exit = exit_frames
        self._need_slow = need_slow
        self._inside = False
        self._run = 0
        self._run_t = 0.0
        self._run_slow = False
        self._start = 0.0
        self._slow = False
        self.visits: list[tuple[float, float | None]] = []

    def step(self, t: float, covered: bool, slow: bool) -> None:
        if not self._inside:
            if not covered:
                self._run = 0
                return
            if self._run == 0:
                self._run_t = t
                self._run_slow = False
            self._run += 1
            self._run_slow = self._run_slow or slow
            if self._run >= self._enter:
                self._inside = True
                self._start = self._run_t
                self._slow = self._run_slow
                self._run = 0
            return
        if covered:
            self._run = 0
            self._slow = self._slow or slow
            return
        if self._run == 0:
            self._run_t = t
        self._run += 1
        if self._run >= self._exit:
            self._close(self._run_t)

    def finish(self) -> None:
        if self._inside:
            self._close(None)

    def _close(self, t_exit: float | None) -> None:
        if self._slow or not self._need_slow:
            self.visits.append((self._start, t_exit))
        self._inside = False
        self._run = 0


def _visits_of_hole(
    samples: SubjectSamples, hole: LayoutHole, params: BarnesParams
) -> list[HoleVisit]:
    covered = _hole_cover(samples, hole) >= params.visit_min_cover
    if not covered.any():
        return []
    max_speed = params.visit_max_speed_cm_s
    need_slow = max_speed is not None
    with np.errstate(invalid="ignore"):
        slow = samples.speed_cm_s < max_speed if max_speed is not None else covered
    debounce = _Debounce(params.visit_enter_frames, params.visit_exit_frames, need_slow)
    t = samples.t_s
    for i in range(len(samples)):
        gap = int(samples.missing_before[i])
        if gap and i > 0:
            # Past ``visit_exit_frames`` uncovered frames the state no longer changes.
            spacing = (t[i] - t[i - 1]) / (gap + 1)
            for k in range(1, min(gap, params.visit_exit_frames) + 1):
                debounce.step(float(t[i - 1] + k * spacing), False, False)
        debounce.step(float(t[i]), bool(covered[i]), bool(covered[i] and slow[i]))
    debounce.finish()
    return [
        HoleVisit(roi=hole.roi.name, offset=hole.offset, t_enter_s=start, t_exit_s=end)
        for start, end in debounce.visits
    ]


def detect_hole_visits(
    samples: SubjectSamples, holes: Sequence[LayoutHole], params: BarnesParams
) -> list[HoleVisit]:
    """Every visit to every hole over the whole recording, sorted by start then offset."""
    visits = [visit for hole in holes for visit in _visits_of_hole(samples, hole, params)]
    visits.sort(key=lambda visit: (visit.t_enter_s, visit.offset))
    return visits


def visits_in_trial(visits: Sequence[HoleVisit], t0: float, trial_end: float) -> list[HoleVisit]:
    """The visits that count for a trial ``[t0, trial_end)``.

    A visit already open at ``t0`` starts at ``t0``; a visit that closed at or before
    ``t0`` is dropped; only visits starting in ``[t0, trial_end)`` count; an exit
    after ``trial_end`` becomes ``None`` (still inside when the trial ended).
    """
    counted: list[HoleVisit] = []
    for visit in visits:
        if visit.t_exit_s is not None and visit.t_exit_s <= t0:
            continue
        start = max(visit.t_enter_s, t0)
        if not start < trial_end:
            continue
        end = visit.t_exit_s
        if end is not None and end > trial_end:
            end = None
        counted.append(HoleVisit(visit.roi, visit.offset, start, end))
    counted.sort(key=lambda visit: (visit.t_enter_s, visit.offset))
    return counted


def path_length_cm(
    samples: SubjectSamples,
    t_from: float,
    t_to: float,
    *,
    pixelcm_x: float,
    pixelcm_y: float,
    gap_threshold_s: float,
) -> float | None:
    """Distance travelled by the centre between ``t_from`` and ``t_to`` (inclusive), cm.

    A step across a gap longer than ``gap_threshold_s`` is not counted (the rule of
    ``distancia_total_cm``). ``None`` without a usable calibration.
    """
    if not (pixelcm_x > 0 and pixelcm_y > 0) or not math.isfinite(pixelcm_x * pixelcm_y):
        return None
    inside = (samples.t_s >= t_from) & (samples.t_s <= t_to)
    t = samples.t_s[inside]
    if len(t) < 2:
        return 0.0
    dt = np.diff(t)
    steps = np.hypot(
        np.diff(samples.cx[inside]) / pixelcm_x, np.diff(samples.cy[inside]) / pixelcm_y
    )
    return float(steps[dt <= gap_threshold_s].sum())
