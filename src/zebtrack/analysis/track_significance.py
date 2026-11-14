"""What counts as an animal in a trajectory (issues #649 and #671).

The report becomes multi-animal (``any_track`` ROI occupancy, a ``por_animal``
sheet, a warning that order metrics mix animals) as soon as the trajectory
holds more than one ``track_id``. A tracker glitch that writes one row under a
new id (a faint box, a one-frame re-id) was enough: a one-rat Barnes video
reported three animals. Such a track cannot be measured as an animal either,
and its rows sit in frames where the real animal is somewhere else.

:func:`screen_short_tracks` removes, FROM THE ANALYSIS ONLY, the rows of tracks
that last less than ``min_duration_s`` -- as long as at least one track lasts
longer -- and says so in a warning. ``3_CoordMovimento`` is never rewritten.
It runs once, at the top of ``AnalysisService.run_full_analysis``, so the
validator's ``unique_tracks``, the behaviour analyser's multi-track flag,
``n_animais`` and ``por_animal`` all see the same trajectory.

A row without a ``track_id`` is not an animal either (#671). Until 8.0 the
single detector wrote, in multi-subject mode, every detection ByteTrack had
held back (an animal's unconfirmed first frame) with ``track_id=None``; in the
parquet it is NaN. The detector no longer writes them, but older trajectories
hold them, so :func:`drop_untracked_rows` removes them FROM THE ANALYSIS
whenever at least one row has an id. A trajectory where NO row has an id (the
tracker failed to start, a recording made without ByteTrack) is one subject
and is kept. :func:`count_subjects` is the one reading of "how many animals",
and :func:`screen_subjects` applies both rules: it is what the report and the
analysis window run, so both see the same subjects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import structlog

from zebtrack.i18n import _

log = structlog.get_logger()

__all__ = [
    "DEFAULT_MIN_TRACK_DURATION_S",
    "TrackScreening",
    "count_subjects",
    "drop_untracked_rows",
    "min_track_duration_from",
    "screen_short_tracks",
    "screen_subjects",
]

#: ``Settings.min_track_duration_s`` default.
DEFAULT_MIN_TRACK_DURATION_S = 0.5


def min_track_duration_from(settings_obj: object) -> float:
    """``settings_obj.min_track_duration_s``, or the default when it is not a number.

    Settings doubles (``Mock``) answer any attribute with another double; a
    threshold made of one would decide what the report counts as an animal.
    """
    value = getattr(settings_obj, "min_track_duration_s", None)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return DEFAULT_MIN_TRACK_DURATION_S
    return float(value)


@dataclass(frozen=True)
class TrackScreening:
    """Outcome of :func:`screen_short_tracks`, :func:`drop_untracked_rows` or
    :func:`screen_subjects`.

    Attributes:
        trajectory: The trajectory to analyse (the input when nothing is dropped).
        dropped_track_ids: Ids whose rows were removed, in input order.
        dropped_rows: Number of rows removed.
        warnings: User-facing warnings, already translated.
    """

    trajectory: pd.DataFrame
    dropped_track_ids: tuple = ()
    dropped_rows: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _format_id(track_id: object) -> str:
    if track_id is None or (isinstance(track_id, float) and np.isnan(track_id)):
        return _("no id")
    if isinstance(track_id, float) and track_id.is_integer():
        return str(int(track_id))
    return str(track_id)


def screen_short_tracks(
    trajectory_df: pd.DataFrame,
    *,
    min_duration_s: float,
    median_dt: float | None,
) -> TrackScreening:
    """Drop, from the analysis, tracks shorter than ``min_duration_s``.

    A track's duration is ``(last timestamp - first timestamp) + median_dt``:
    the time it covers, sampling interval included, so one row lasts one
    interval whatever ``analysis_interval_frames`` is. Rows without a
    ``track_id`` form one group, as they do in the behaviour analyser.

    Args:
        trajectory_df: Trajectory with ``track_id`` and ``timestamp`` columns.
        min_duration_s: Shortest track that counts as an animal; ``<= 0``
            disables the screening.
        median_dt: The recording's median sampling interval
            (``TimeBase.median_dt``); ``None`` counts as 0.

    Returns:
        The screened trajectory and what was removed. Nothing is removed when
        there is a single track, no timestamp, or no track reaches the
        threshold (then a warning says the tracks could not be told apart).
    """
    if (
        min_duration_s <= 0
        or trajectory_df.empty
        or "track_id" not in trajectory_df.columns
        or "timestamp" not in trajectory_df.columns
    ):
        return TrackScreening(trajectory_df)

    groups = trajectory_df.groupby("track_id", dropna=False, sort=False)["timestamp"]
    if groups.ngroups <= 1:
        return TrackScreening(trajectory_df)

    step = float(median_dt) if median_dt is not None and np.isfinite(median_dt) else 0.0
    durations = (groups.max() - groups.min()).astype(float) + step
    short = durations[durations < min_duration_s]
    if short.empty:
        return TrackScreening(trajectory_df)

    if len(short) == len(durations):
        log.warning(
            "analysis.track_screening.all_tracks_short",
            tracks=len(durations),
            min_duration_s=min_duration_s,
        )
        return TrackScreening(
            trajectory_df,
            warnings=(
                _(
                    "Every track in this trajectory lasts less than {min_s:g} s, so "
                    "short tracker glitches cannot be told apart from animals; all "
                    "{count} tracks were kept."
                ).format(min_s=min_duration_s, count=len(durations)),
            ),
        )

    # Identified ids in ascending order, rows without id last: a stable warning.
    short_ids = tuple(sorted(short.index, key=lambda i: (pd.isna(i), 0 if pd.isna(i) else i)))
    dropped = trajectory_df["track_id"].isin([i for i in short_ids if pd.notna(i)])
    if any(pd.isna(i) for i in short_ids):
        dropped |= trajectory_df["track_id"].isna()
    kept = trajectory_df.loc[~dropped]
    dropped_rows = int(dropped.sum())
    log.info(
        "analysis.track_screening.dropped",
        track_ids=[_format_id(i) for i in short_ids],
        rows=dropped_rows,
        min_duration_s=min_duration_s,
    )
    warning = _(
        "{count} track(s) shorter than {min_s:g} s were left out of the analysis "
        "as tracker glitches, not animals (track_id {ids}; {rows} row(s)). The "
        "trajectory file keeps them."
    ).format(
        count=len(short_ids),
        min_s=min_duration_s,
        ids=", ".join(_format_id(i) for i in short_ids),
        rows=dropped_rows,
    )
    return TrackScreening(kept, short_ids, dropped_rows, (warning,))


def drop_untracked_rows(trajectory_df: pd.DataFrame) -> TrackScreening:
    """Drop, from the analysis, rows without a ``track_id`` when others have one.

    Rows without an id are detections ByteTrack never confirmed (#671). In a
    multi-animal frame they can belong to DIFFERENT animals, so grouping them as
    one subject draws a path that jumps between animals and adds one to the
    animal count. When no row has an id, the whole trajectory is one subject
    and nothing is dropped.

    Args:
        trajectory_df: Trajectory with a ``track_id`` column (any index).

    Returns:
        The screened trajectory (a new frame when rows were dropped, otherwise
        ``trajectory_df`` itself) and a warning naming how many rows left.
    """
    if trajectory_df.empty or "track_id" not in trajectory_df.columns:
        return TrackScreening(trajectory_df)
    untracked = trajectory_df["track_id"].isna()
    if not untracked.any() or untracked.all():
        return TrackScreening(trajectory_df)

    dropped_rows = int(untracked.sum())
    log.info("analysis.track_screening.untracked_dropped", rows=dropped_rows)
    warning = _(
        "{rows} row(s) without a track_id were left out of the analysis: the "
        "tracker never confirmed them, so they belong to no animal. The "
        "trajectory file keeps them."
    ).format(rows=dropped_rows)
    kept = trajectory_df.loc[~untracked.to_numpy(dtype=bool)].copy()
    return TrackScreening(kept, (), dropped_rows, (warning,))


def count_subjects(trajectory_df: pd.DataFrame) -> int:
    """How many animals a trajectory holds: the one reading every counter uses.

    Distinct identified ``track_id`` values; rows without an id are not an
    animal (#671), unless NO row has one, in which case the trajectory is one
    unidentified subject. Without a ``track_id`` column it is one subject too;
    an empty trajectory holds none.
    """
    if trajectory_df.empty:
        return 0
    if "track_id" not in trajectory_df.columns:
        return 1
    return max(int(trajectory_df["track_id"].nunique(dropna=True)), 1)


def screen_subjects(
    trajectory_df: pd.DataFrame,
    *,
    min_duration_s: float,
    median_dt: float | None,
) -> TrackScreening:
    """Both rules of what is an animal: rows without id first, then short tracks.

    The untracked rows go first so a long run of them can never be the "longer
    track" that lets real short tracks be screened, nor survive as one.

    Args:
        trajectory_df: Trajectory with ``track_id`` and ``timestamp`` columns.
        min_duration_s: See :func:`screen_short_tracks`.
        median_dt: See :func:`screen_short_tracks`.

    Returns:
        The trajectory both screenings left, with their removals and warnings
        combined.
    """
    untracked = drop_untracked_rows(trajectory_df)
    short = screen_short_tracks(
        untracked.trajectory, min_duration_s=min_duration_s, median_dt=median_dt
    )
    return TrackScreening(
        short.trajectory,
        short.dropped_track_ids,
        untracked.dropped_rows + short.dropped_rows,
        untracked.warnings + short.warnings,
    )
