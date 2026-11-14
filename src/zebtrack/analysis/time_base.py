"""Time base of a recording: which clock dates it, at what rate, for how long.

Before this module every report took ``settings.video_processing.fps`` (30 by
default) as the truth and computed the recording length as ``len(df) / fps``.
That counts ROWS, not time: it doubles with two tracks, halves when the
subject is missing for half the video and shrinks ``analysis_interval_frames``
times when only every N-th frame is analysed. A 9.9 fps variable-frame-rate
video was read as 30 fps.

:func:`resolve_time_base` picks the time base from the best source available,
in this order (ADR-011 § Clocks):

1. the heartbeat rows (``class_id == -1``) of the ``3c_Objetos_`` sidecar —
   one per processed frame, even with no detection;
2. the live frame ledger (``6_FrameLedger_``) — the capture clock;
3. the UNIQUE timestamps of the trajectory — the PTS for pre-recorded video;
4. the caller's ``fallback_fps`` (``settings.video_processing.fps``), always
   with a warning, because nothing in the recording backs it.

``duration_s`` is ``(t_last - t_first) + median_dt`` over unique timestamps:
the last sample covers one interval too. Never rows divided by a rate.

:func:`retime_from_ledger` re-dates a live trajectory with the capture clock.
The live ``timestamp`` column is a PROCESSING clock (after the queue and the
inference) and must never date anything; the Parquet on disk is left alone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import structlog

from zebtrack.i18n import _

log = structlog.get_logger()

SOURCE_HEARTBEAT = "objects_heartbeat"
SOURCE_LEDGER = "ledger"
SOURCE_TRAJECTORY = "trajectory_timestamps"
SOURCE_FALLBACK = "fallback_fps"
SOURCE_NONE = "none"

#: ``class_id`` of the per-frame heartbeat rows in ``3c_Objetos_`` (ADR-010).
HEARTBEAT_CLASS_ID = -1

#: Key under ``DataFrame.attrs`` where :func:`retime_from_ledger` leaves its
#: warnings, so the signature can stay ``-> DataFrame``.
TIME_WARNINGS_ATTR = "zebtrack_time_warnings"

type LedgerInput = Sequence[Mapping[str, Any]] | pd.DataFrame


@dataclass(frozen=True)
class TimeBase:
    """How a recording is dated.

    Attributes:
        fps_sampling: Rate of the ANALYSED samples (unique timestamps), as
            ``(n - 1) / span``. With ``analysis_interval_frames=10`` on a
            10 fps video this is 1.0.
        fps_video: Rate of the underlying video or capture. From the ``frame``
            numbers when they exist (``Δframe / Δt``), otherwise equal to
            ``fps_sampling``.
        duration_s: ``(t_last - t_first) + median_dt``; ``None`` when nothing
            dates the recording.
        t_first: First timestamp on the source clock, in seconds.
        t_last: Last timestamp on the source clock, in seconds.
        median_dt: Median interval between consecutive unique timestamps.
        source: One of the ``SOURCE_*`` constants.
        warnings: User-facing warnings, already translated.
    """

    fps_sampling: float | None
    fps_video: float | None
    duration_s: float | None
    t_first: float | None
    t_last: float | None
    median_dt: float | None
    source: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ClockStats:
    t_first: float
    t_last: float
    median_dt: float
    fps_sampling: float
    fps_video: float

    @property
    def duration_s(self) -> float:
        return (self.t_last - self.t_first) + self.median_dt


def _to_seconds(values: pd.Series | pd.Index) -> np.ndarray:
    """Any time-like series as float seconds (``NaN`` where unreadable)."""
    series = pd.Series(values)
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds().to_numpy(dtype=float)
    if pd.api.types.is_datetime64_any_dtype(series):
        return (series - series.min()).dt.total_seconds().to_numpy(dtype=float)
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _clock_stats(times: np.ndarray, frames: np.ndarray | None) -> _ClockStats | None:
    """Rate and extent of a clock, over its UNIQUE finite timestamps.

    Returns ``None`` with fewer than two distinct instants: a single instant
    has no interval to derive a rate from.
    """
    finite = np.isfinite(times)
    times = times[finite]
    if frames is not None:
        frames = frames[finite]

    unique = np.unique(times)
    if unique.size < 2:
        return None

    t_first = float(unique[0])
    t_last = float(unique[-1])
    span = t_last - t_first
    median_dt = float(np.median(np.diff(unique)))
    # Mean rate, not 1 / median_dt: on a variable frame rate the median
    # interval describes the typical frame, while the number of intervals over
    # the span is the rate the recording actually achieved.
    fps_sampling = (unique.size - 1) / span

    fps_video = fps_sampling
    if frames is not None and frames.size:
        finite_frames = np.isfinite(frames)
        first_frames = frames[(times == t_first) & finite_frames]
        last_frames = frames[(times == t_last) & finite_frames]
        if first_frames.size and last_frames.size:
            frame_span = float(last_frames.max()) - float(first_frames.min())
            if frame_span > 0:
                fps_video = frame_span / span

    return _ClockStats(
        t_first=t_first,
        t_last=t_last,
        median_dt=median_dt,
        fps_sampling=fps_sampling,
        fps_video=fps_video,
    )


def _frames_of(df: pd.DataFrame) -> np.ndarray | None:
    if "frame" not in df.columns:
        return None
    return pd.to_numeric(df["frame"], errors="coerce").to_numpy(dtype=float)


def _trajectory_times(df: pd.DataFrame) -> np.ndarray | None:
    if "timestamp" in df.columns:
        return _to_seconds(df["timestamp"])
    if isinstance(df.index, pd.TimedeltaIndex):
        return _to_seconds(df.index)
    return None


def _from_heartbeat(objects_df: pd.DataFrame | None) -> _ClockStats | None:
    if objects_df is None or objects_df.empty or "class_id" not in objects_df.columns:
        return None
    class_ids = pd.to_numeric(objects_df["class_id"], errors="coerce")
    heartbeat = objects_df[class_ids == HEARTBEAT_CLASS_ID]
    if heartbeat.empty:
        return None
    # ``t_event_s`` is the event clock (PTS or capture); ``timestamp`` mirrors
    # the trajectory column and is only the fallback.
    column = "t_event_s" if "t_event_s" in heartbeat.columns else "timestamp"
    if column not in heartbeat.columns:
        return None
    return _clock_stats(_to_seconds(heartbeat[column]), _frames_of(heartbeat))


def _ledger_records(ledger: LedgerInput | None) -> list[Mapping[str, Any]]:
    if ledger is None:
        return []
    if isinstance(ledger, pd.DataFrame):
        return list(ledger.to_dict("records"))
    return list(ledger)


def _capture_time(row: Mapping[str, Any]) -> float | None:
    value = row.get("t_capture_perf")
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _from_ledger(
    ledger: LedgerInput | None, trajectory_frames: np.ndarray | None
) -> _ClockStats | None:
    """Capture clock of a live session, relative to its first capture.

    Duration and video rate come from EVERY captured frame — the ledger is the
    session timeline, and a frame without a detection was still recorded.
    The sampling rate comes from the frames that were analysed: the ones the
    trajectory carries, else the ones the capture thread marked for analysis.
    """
    records = _ledger_records(ledger)
    timed = [
        (int(row["pipeline_frame"]), t) for row in records if (t := _capture_time(row)) is not None
    ]
    if len(timed) < 2:
        return None

    frames = np.array([frame for frame, _t in timed], dtype=float)
    times = np.array([t for _frame, t in timed], dtype=float)
    # Same zero as the anchor's ``t0_perf``: the first timed capture.
    times = times - times.min()

    stats = _clock_stats(times, frames)
    if stats is None:
        return None

    analysed: np.ndarray | None = None
    if trajectory_frames is not None:
        analysed = np.isin(frames, trajectory_frames[np.isfinite(trajectory_frames)])
    if analysed is None or analysed.sum() < 2:
        flags = {int(row["pipeline_frame"]): bool(row.get("is_analysis_frame")) for row in records}
        analysed = np.array([flags.get(int(frame), False) for frame in frames])
    if analysed.sum() >= 2:
        sampled = _clock_stats(times[analysed], None)
        if sampled is not None:
            stats = _ClockStats(
                t_first=stats.t_first,
                t_last=stats.t_last,
                median_dt=stats.median_dt,
                fps_sampling=sampled.fps_sampling,
                fps_video=stats.fps_video,
            )
    return stats


def _as_time_base(stats: _ClockStats, source: str) -> TimeBase:
    return TimeBase(
        fps_sampling=stats.fps_sampling,
        fps_video=stats.fps_video,
        duration_s=stats.duration_s,
        t_first=stats.t_first,
        t_last=stats.t_last,
        median_dt=stats.median_dt,
        source=source,
    )


def _fallback(
    df: pd.DataFrame, times: np.ndarray | None, frames: np.ndarray | None, fps: float
) -> TimeBase:
    """Nominal rate with nothing in the recording to back it."""
    finite_times = times[np.isfinite(times)] if times is not None else np.zeros(0)
    finite_frames = frames[np.isfinite(frames)] if frames is not None else np.zeros(0)

    duration: float | None = None
    if finite_frames.size:
        # Unique frames, not rows: two tracks on frame 0 are one frame.
        duration = (float(finite_frames.max()) - float(finite_frames.min()) + 1.0) / fps
    elif finite_times.size:
        duration = float(np.unique(finite_times).size) / fps
    elif not df.empty:
        duration = float(len(df)) / fps

    message = _(
        "The recording carries no usable timestamps, so its time base could not be "
        "measured. The configured {fps:g} fps was used instead; durations and rates "
        "in this report depend on that value being right."
    ).format(fps=fps)
    log.warning(
        "time_base.resolve.fallback_fps",
        fallback_fps=fps,
        rows=len(df),
        duration_s=duration,
    )
    return TimeBase(
        fps_sampling=fps,
        fps_video=fps,
        duration_s=duration,
        t_first=float(finite_times.min()) if finite_times.size else None,
        t_last=float(finite_times.max()) if finite_times.size else None,
        median_dt=1.0 / fps,
        source=SOURCE_FALLBACK,
        warnings=(message,),
    )


def resolve_time_base(
    trajectory_df: pd.DataFrame,
    *,
    objects_df: pd.DataFrame | None = None,
    ledger: LedgerInput | None = None,
    fallback_fps: float | None = None,
) -> TimeBase:
    """Pick the time base of a recording from the best available source.

    Args:
        trajectory_df: The trajectory, with a ``timestamp`` column (seconds or
            ``Timedelta``) or a ``TimedeltaIndex``, and ideally ``frame``.
        objects_df: The ``3c_Objetos_`` sidecar; only its heartbeat rows
            (``class_id == -1``) are read.
        ledger: Rows of ``6_FrameLedger_`` (as returned by
            :func:`zebtrack.core.recording.frame_ledger.load_ledger`, or a
            DataFrame with the same columns).
        fallback_fps: The caller's ``settings.video_processing.fps``. Used only
            when no source above dates the recording, and always with a warning.

    Returns:
        A frozen :class:`TimeBase`.
    """
    frames = _frames_of(trajectory_df)
    times = _trajectory_times(trajectory_df)

    heartbeat = _from_heartbeat(objects_df)
    if heartbeat is not None:
        return _as_time_base(heartbeat, SOURCE_HEARTBEAT)

    from_ledger = _from_ledger(ledger, frames)
    if from_ledger is not None:
        return _as_time_base(from_ledger, SOURCE_LEDGER)

    if times is not None:
        from_pts = _clock_stats(times, frames)
        if from_pts is not None:
            return _as_time_base(from_pts, SOURCE_TRAJECTORY)

    if fallback_fps is not None and math.isfinite(fallback_fps) and fallback_fps > 0:
        return _fallback(trajectory_df, times, frames, float(fallback_fps))

    log.warning("time_base.resolve.unavailable", rows=len(trajectory_df))
    return TimeBase(
        fps_sampling=None,
        fps_video=None,
        duration_s=None,
        t_first=None,
        t_last=None,
        median_dt=None,
        source=SOURCE_NONE,
        warnings=(
            _(
                "The time base of the recording could not be determined: it has no "
                "usable timestamps and no frame rate was configured."
            ),
        ),
    )


def _with_warnings(df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    out = df.copy(deep=False)
    out.attrs = {**df.attrs, TIME_WARNINGS_ATTR: list(warnings)}
    return out


def retime_from_ledger(
    df: pd.DataFrame, ledger_rows: LedgerInput | None, anchor: Mapping[str, Any] | None
) -> pd.DataFrame:
    """Re-date a live trajectory with the capture clock of its frame ledger.

    Only the time axis changes — the ``timestamp`` column every analyser turns
    into its index — and only in memory: the result is a copy, the Parquet is
    never rewritten. ``timestamp`` becomes ``t_capture_perf - anchor.t0_perf``
    through the join ``pipeline_frame == frame``.

    The swap is all or nothing. When any row has no capture instant (frame not
    in the ledger, or captured without a ``perf_counter`` value) the frame is
    returned intact: half the rows on the capture clock and half on the
    processing clock would be worse than either clock alone.

    Warnings are left in ``result.attrs[TIME_WARNINGS_ATTR]`` and logged.
    """
    rows = _ledger_records(ledger_rows)
    if not rows:
        log.warning("time_base.retime.no_ledger", rows=len(df))
        return _with_warnings(
            df,
            [
                _(
                    "No frame ledger was found for this live session; its times "
                    "come from the processing clock, not from the capture instant."
                )
            ],
        )
    if "frame" not in df.columns or "timestamp" not in df.columns:
        log.warning("time_base.retime.missing_columns", columns=list(df.columns))
        return _with_warnings(
            df,
            [
                _(
                    "The trajectory has no frame/timestamp columns to join with the "
                    "frame ledger; it was not re-timed."
                )
            ],
        )

    # Imported here: ``zebtrack.core.recording``'s package import pulls the
    # analysis service, which imports this module (circular at import time).
    from zebtrack.core.recording.frame_ledger import index_by_pipeline_frame

    by_frame = index_by_pipeline_frame([dict(row) for row in rows])
    capture = {frame: t for frame, row in by_frame.items() if (t := _capture_time(row)) is not None}

    anchor = anchor or {}
    t0_raw = anchor.get("t0_perf")
    t0 = float(t0_raw) if t0_raw is not None else min(capture.values(), default=0.0)

    frames = pd.to_numeric(df["frame"], errors="coerce")
    captured = frames.map(lambda f: capture.get(int(f)) if pd.notna(f) else None)
    missing = int(captured.isna().sum())
    if missing:
        log.warning(
            "time_base.retime.unmatched_frames",
            unmatched=missing,
            rows=len(df),
        )
        return _with_warnings(
            df,
            [
                _(
                    "{count} trajectory rows have no capture time in the frame ledger; "
                    "the session was not re-timed and keeps the processing clock."
                ).format(count=missing)
            ],
        )

    out = df.copy()
    out["timestamp"] = captured.astype(float).to_numpy() - t0
    out.attrs = {**df.attrs, TIME_WARNINGS_ATTR: []}
    log.info("time_base.retime.applied", rows=len(out), t0_perf=t0)
    return out
