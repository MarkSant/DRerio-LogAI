"""What counts as an animal: short tracks (#649) and rows without an id (#671)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.track_significance import (
    DEFAULT_MIN_TRACK_DURATION_S,
    count_subjects,
    drop_untracked_rows,
    min_track_duration_from,
    screen_short_tracks,
    screen_subjects,
)


def _rows(track_id, times):
    return pd.DataFrame({"timestamp": list(times), "track_id": [track_id] * len(times)})


def _traj(*parts):
    return pd.concat(parts, ignore_index=True)


def test_a_one_row_track_next_to_a_long_one_is_left_out_with_a_warning():
    df = _traj(_rows(1, np.arange(0, 6, 0.1)), _rows(2, [3.0]), _rows(3, [3.0]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.1)

    assert sorted(out.trajectory["track_id"].unique()) == [1]
    assert out.dropped_track_ids == (2, 3)
    assert out.dropped_rows == 2
    assert len(out.warnings) == 1
    assert "track_id 2, 3; 2 row(s)" in out.warnings[0]


def test_duration_is_span_plus_one_interval_so_sparse_sampling_is_fair():
    # Interval 10 at 30 fps: one row every 1/3 s. Two rows span 1/3 s + 1/3 s.
    df = _traj(_rows(1, np.arange(0, 6, 1 / 3)), _rows(2, [3.0, 3.0 + 1 / 3]), _rows(3, [4.0]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=1 / 3)

    assert sorted(out.trajectory["track_id"].unique()) == [1, 2]
    assert out.dropped_track_ids == (3,)


def test_exactly_the_threshold_is_kept():
    df = _traj(_rows(1, np.arange(0, 6, 0.1)), _rows(2, [3.0, 3.25]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.25)

    assert out.dropped_track_ids == ()
    assert out.trajectory is df


def test_rows_without_id_form_one_group_like_in_the_behaviour_analyser():
    df = _traj(_rows(1, np.arange(0, 6, 0.1)), _rows(np.nan, [2.0]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.1)

    assert out.trajectory["track_id"].notna().all()
    assert out.dropped_rows == 1
    assert "no id" in out.warnings[0]


def test_when_every_track_is_short_all_are_kept_and_it_says_so():
    df = _traj(_rows(1, [0.0, 0.1]), _rows(2, [0.0]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.1)

    assert out.trajectory is df
    assert out.dropped_track_ids == ()
    assert len(out.warnings) == 1
    assert "2 tracks were kept" in out.warnings[0]


@pytest.mark.parametrize(
    "df",
    [
        _rows(1, [0.0]),  # a single track
        pd.DataFrame({"timestamp": [0.0, 0.1]}),  # no track_id
        pd.DataFrame({"track_id": [1, 2]}),  # no timestamp
        pd.DataFrame({"timestamp": [], "track_id": []}),
    ],
)
def test_nothing_to_screen(df):
    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.1)

    assert out.trajectory is df
    assert out.warnings == ()


def test_zero_disables_it():
    df = _traj(_rows(1, np.arange(0, 6, 0.1)), _rows(2, [3.0]))

    assert screen_short_tracks(df, min_duration_s=0.0, median_dt=0.1).trajectory is df


def test_unknown_interval_counts_as_zero():
    df = _traj(_rows(1, np.arange(0, 6, 0.1)), _rows(2, [3.0, 3.45]))

    out = screen_short_tracks(df, min_duration_s=0.5, median_dt=None)

    assert out.dropped_track_ids == (2,)


def test_threshold_comes_from_settings_or_the_default():
    assert min_track_duration_from(SimpleNamespace(min_track_duration_s=1.5)) == 1.5
    assert min_track_duration_from(SimpleNamespace(min_track_duration_s=0)) == 0.0
    assert min_track_duration_from(Mock()) == DEFAULT_MIN_TRACK_DURATION_S
    assert min_track_duration_from(SimpleNamespace(min_track_duration_s=True)) == (
        DEFAULT_MIN_TRACK_DURATION_S
    )
    assert min_track_duration_from(None) == DEFAULT_MIN_TRACK_DURATION_S


# ---------------------------------------------------------------------------
# #671: a row without a track_id is not an animal.
# ---------------------------------------------------------------------------


def _two_animals_and_an_untracked_run():
    """Two 6 s animals plus 3 s of rows ByteTrack never confirmed (a pre-fix parquet)."""
    return _traj(
        _rows(1, np.arange(0, 6, 0.1)),
        _rows(2, np.arange(0, 6, 0.1)),
        _rows(np.nan, np.arange(1, 4, 0.1)),
    )


def test_rows_without_id_next_to_identified_tracks_leave_the_analysis():
    df = _two_animals_and_an_untracked_run()
    rows_before = len(df)

    out = drop_untracked_rows(df)

    assert out.trajectory["track_id"].notna().all()
    assert sorted(out.trajectory["track_id"].unique()) == [1, 2]
    assert out.dropped_rows == 30
    assert len(out.warnings) == 1
    assert "30 row(s)" in out.warnings[0]
    assert len(df) == rows_before  # the caller's frame is untouched


def test_a_trajectory_without_any_id_is_one_subject_and_is_kept():
    df = _rows(np.nan, np.arange(0, 3, 0.1))

    out = drop_untracked_rows(df)

    assert out.trajectory is df
    assert out.warnings == ()
    assert count_subjects(df) == 1


@pytest.mark.parametrize(
    "df",
    [
        _rows(1, [0.0, 0.1]),
        pd.DataFrame({"timestamp": [0.0, 0.1]}),  # no track_id
        pd.DataFrame({"timestamp": [], "track_id": []}),
    ],
)
def test_nothing_to_drop(df):
    out = drop_untracked_rows(df)

    assert out.trajectory is df
    assert out.dropped_rows == 0


@pytest.mark.parametrize(
    ("df", "expected"),
    [
        (_two_animals_and_an_untracked_run(), 2),  # NaN rows are not a third animal
        (_rows(np.nan, [0.0, 0.1]), 1),  # all unidentified: one subject
        (pd.DataFrame({"timestamp": [0.0, 0.1]}), 1),  # no track_id column
        (pd.DataFrame({"timestamp": [], "track_id": []}), 0),  # nothing recorded
        (_traj(_rows(7, [0.0]), _rows(3, [0.1]), _rows(7, [0.2])), 2),
    ],
)
def test_count_subjects(df, expected):
    assert count_subjects(df) == expected


def test_a_long_untracked_run_is_not_an_animal_after_the_screening():
    """The short-track screening alone kept it: 3 s of NaN rows outlast 0.5 s."""
    df = _two_animals_and_an_untracked_run()
    kept = screen_short_tracks(df, min_duration_s=0.5, median_dt=0.1).trajectory
    assert kept["track_id"].isna().any()

    out = screen_subjects(df, min_duration_s=0.5, median_dt=0.1)

    assert out.trajectory["track_id"].notna().all()
    assert count_subjects(out.trajectory) == 2
    assert out.dropped_rows == 30


def test_screen_subjects_applies_both_rules_and_keeps_both_warnings():
    df = _traj(_two_animals_and_an_untracked_run(), _rows(3, [2.0]))

    out = screen_subjects(df, min_duration_s=0.5, median_dt=0.1)

    assert sorted(out.trajectory["track_id"].unique()) == [1, 2]
    assert out.dropped_track_ids == (3,)
    assert out.dropped_rows == 31
    assert len(out.warnings) == 2


def test_screen_subjects_with_the_screening_disabled_still_drops_untracked_rows():
    df = _traj(_two_animals_and_an_untracked_run(), _rows(3, [2.0]))

    out = screen_subjects(df, min_duration_s=0.0, median_dt=0.1)

    assert sorted(out.trajectory["track_id"].unique()) == [1, 2, 3]
    assert out.dropped_rows == 30
