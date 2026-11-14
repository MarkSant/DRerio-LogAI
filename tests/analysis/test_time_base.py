"""Tests for :mod:`zebtrack.analysis.time_base`.

The time base decides how long a recording lasted and at what rate it was
sampled. Before it existed every report took ``settings.video_processing.fps``
(30) as the truth and computed the duration as ``len(df) / fps`` — rows, not
time. These tests pin the source order and the arithmetic that replaced it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import structlog.testing

from zebtrack.analysis.time_base import (
    SOURCE_FALLBACK,
    SOURCE_HEARTBEAT,
    SOURCE_LEDGER,
    SOURCE_NONE,
    SOURCE_TRAJECTORY,
    TIME_WARNINGS_ATTR,
    TimeBase,
    resolve_time_base,
    retime_from_ledger,
)


def _trajectory(timestamps, frames=None, track_ids=None) -> pd.DataFrame:
    timestamps = list(timestamps)
    data: dict[str, object] = {"timestamp": timestamps}
    data["frame"] = list(frames) if frames is not None else list(range(len(timestamps)))
    data["track_id"] = list(track_ids) if track_ids is not None else [1] * len(timestamps)
    data["x_center_px"] = np.linspace(0.0, 10.0, len(timestamps))
    data["y_center_px"] = np.zeros(len(timestamps))
    return pd.DataFrame(data)


def _ledger_rows(perf_times, first_frame=1, analysis_every=1):
    rows = []
    for offset, t in enumerate(perf_times):
        frame = first_frame + offset
        rows.append(
            {
                "pipeline_frame": frame,
                "video_frame_index": offset,
                "t_capture_perf": t,
                "t_capture_wall": None if t is None else 1_700_000_000.0 + t,
                "outcome": "written",
                "is_analysis_frame": frame % analysis_every == 0,
                "queued_for_analysis": frame % analysis_every == 0,
            }
        )
    return rows


class TestTrajectorySource:
    def test_cfr_ten_fps_hundred_frames_lasts_ten_seconds(self) -> None:
        df = _trajectory(np.arange(100) / 10.0)

        tb = resolve_time_base(df, fallback_fps=30.0)

        assert tb.source == SOURCE_TRAJECTORY
        assert tb.duration_s == pytest.approx(10.0)
        assert tb.fps_sampling == pytest.approx(10.0)
        assert tb.fps_video == pytest.approx(10.0)
        assert tb.median_dt == pytest.approx(0.1)
        assert tb.t_first == pytest.approx(0.0)
        assert tb.t_last == pytest.approx(9.9)
        assert tb.warnings == ()

    def test_settings_fps_does_not_override_pts(self) -> None:
        """A 30 fps setting must not turn a 10 fps recording into 3.3 s."""
        df = _trajectory(np.arange(100) / 10.0)

        at_30 = resolve_time_base(df, fallback_fps=30.0)
        at_5 = resolve_time_base(df, fallback_fps=5.0)

        assert at_30.duration_s == pytest.approx(10.0)
        assert at_30 == at_5

    def test_two_tracks_count_time_not_rows(self) -> None:
        """2 tracks x 100 frames at 10 fps is 10 s, not the 20 s rows would give."""
        t = np.arange(100) / 10.0
        df = _trajectory(
            np.concatenate([t, t]),
            frames=np.concatenate([np.arange(100), np.arange(100)]),
            track_ids=[1] * 100 + [2] * 100,
        )

        tb = resolve_time_base(df, fallback_fps=10.0)

        assert tb.duration_s == pytest.approx(10.0)
        assert tb.fps_sampling == pytest.approx(10.0)

    def test_frames_without_subject_do_not_shorten_the_recording(self) -> None:
        """Half the frames with no detection (a gap in the middle) is still 10 s."""
        keep = np.r_[0:25, 75:100]
        df = _trajectory(keep / 10.0, frames=keep)

        tb = resolve_time_base(df, fallback_fps=10.0)

        assert tb.duration_s == pytest.approx(10.0)
        assert tb.median_dt == pytest.approx(0.1)

    def test_analysis_interval_ten_reflects_real_time(self) -> None:
        """Every 10th frame of a 10 fps video: 10 samples spanning 10 s."""
        frames = np.arange(0, 100, 10)
        df = _trajectory(frames / 10.0, frames=frames)

        tb = resolve_time_base(df, fallback_fps=10.0)

        assert tb.duration_s == pytest.approx(10.0)
        assert tb.fps_sampling == pytest.approx(1.0)
        assert tb.fps_video == pytest.approx(10.0)

    def test_variable_frame_rate_uses_the_mean_rate(self) -> None:
        """Intervals of 98-142 ms (Barnes-like VFR) resolve to ~9.9 fps.

        The pattern is 13 intervals of 98 ms and one of 142 ms. The median
        interval alone would claim 10.2 fps; the effective rate is the number of
        intervals over the span.
        """
        pattern = [0.098] * 13 + [0.142]
        intervals = np.tile(pattern, 10)
        timestamps = np.concatenate([[0.0], np.cumsum(intervals)])
        df = _trajectory(timestamps)

        tb = resolve_time_base(df, fallback_fps=30.0)

        assert tb.fps_sampling == pytest.approx(9.9, abs=0.05)
        assert tb.median_dt == pytest.approx(0.098)
        span = timestamps[-1] - timestamps[0]
        assert tb.duration_s == pytest.approx(span + 0.098)

    def test_duration_adds_one_median_interval(self) -> None:
        """The last sample covers one interval: 3 samples at 1 Hz last 3 s, not 2."""
        df = _trajectory([5.0, 6.0, 7.0])

        tb = resolve_time_base(df)

        assert tb.duration_s == pytest.approx(3.0)
        assert tb.t_first == pytest.approx(5.0)
        assert tb.t_last == pytest.approx(7.0)

    def test_timedelta_timestamps_are_accepted(self) -> None:
        df = _trajectory(pd.to_timedelta(np.arange(20) / 10.0, unit="s"))

        tb = resolve_time_base(df)

        assert tb.source == SOURCE_TRAJECTORY
        assert tb.duration_s == pytest.approx(2.0)

    def test_timedelta_index_without_column(self) -> None:
        df = pd.DataFrame(
            {"frame": np.arange(20)},
            index=pd.to_timedelta(np.arange(20) / 10.0, unit="s"),
        )

        tb = resolve_time_base(df)

        assert tb.source == SOURCE_TRAJECTORY
        assert tb.duration_s == pytest.approx(2.0)

    def test_without_frame_column_video_rate_equals_sampling_rate(self) -> None:
        df = pd.DataFrame({"timestamp": np.arange(10) / 5.0})

        tb = resolve_time_base(df)

        assert tb.fps_sampling == pytest.approx(5.0)
        assert tb.fps_video == pytest.approx(5.0)


class TestFallback:
    def test_single_timestamp_falls_back_with_a_warning(self, caplog) -> None:
        df = _trajectory([0.0, 0.0, 0.0], frames=[0, 1, 2])

        tb = resolve_time_base(df, fallback_fps=30.0)

        assert tb.source == SOURCE_FALLBACK
        assert tb.fps_sampling == pytest.approx(30.0)
        assert tb.fps_video == pytest.approx(30.0)
        # Frames 0..2 at 30 fps: three frames, one tenth of a second.
        assert tb.duration_s == pytest.approx(3 / 30.0)
        assert len(tb.warnings) == 1
        assert "30" in tb.warnings[0]

    def test_fallback_counts_unique_frames_not_rows(self) -> None:
        df = _trajectory([0.0] * 4, frames=[0, 0, 1, 1], track_ids=[1, 2, 1, 2])

        tb = resolve_time_base(df, fallback_fps=10.0)

        assert tb.source == SOURCE_FALLBACK
        assert tb.duration_s == pytest.approx(2 / 10.0)

    def test_fallback_logs(self) -> None:
        with structlog.testing.capture_logs() as logs:
            resolve_time_base(_trajectory([1.0], frames=[0]), fallback_fps=30.0)

        events = [entry["event"] for entry in logs if entry["log_level"] == "warning"]
        assert "time_base.resolve.fallback_fps" in events

    def test_pts_source_does_not_warn(self) -> None:
        with structlog.testing.capture_logs() as logs:
            resolve_time_base(_trajectory(np.arange(10) / 10.0), fallback_fps=30.0)

        assert not [entry for entry in logs if entry["log_level"] == "warning"]

    def test_nothing_usable_yields_none_source(self) -> None:
        tb = resolve_time_base(pd.DataFrame({"timestamp": [1.0]}))

        assert tb.source == SOURCE_NONE
        assert tb.duration_s is None
        assert tb.fps_sampling is None
        assert tb.warnings

    def test_non_positive_fallback_is_not_a_rate(self) -> None:
        tb = resolve_time_base(pd.DataFrame({"timestamp": [1.0]}), fallback_fps=0.0)

        assert tb.source == SOURCE_NONE

    def test_empty_trajectory_uses_fallback(self) -> None:
        tb = resolve_time_base(pd.DataFrame(), fallback_fps=25.0)

        assert tb.source == SOURCE_FALLBACK
        assert tb.fps_video == pytest.approx(25.0)
        assert tb.duration_s is None


class TestSourceOrder:
    def test_heartbeat_wins_over_ledger_and_trajectory(self) -> None:
        df = _trajectory(np.arange(10) / 10.0)
        objects = pd.DataFrame(
            {
                "frame": np.arange(40),
                "timestamp": np.arange(40) / 4.0,
                "t_event_s": np.arange(40) / 4.0,
                "class_id": [-1] * 40,
            }
        )
        ledger = _ledger_rows(list(np.arange(50) / 20.0))

        tb = resolve_time_base(df, objects_df=objects, ledger=ledger, fallback_fps=30.0)

        assert tb.source == SOURCE_HEARTBEAT
        assert tb.fps_sampling == pytest.approx(4.0)
        assert tb.duration_s == pytest.approx(10.0)

    def test_heartbeat_ignores_detection_rows(self) -> None:
        objects = pd.DataFrame(
            {
                "frame": [0, 0, 1, 1, 2],
                "t_event_s": [0.0, 0.0, 0.5, 0.5, 1.0],
                "timestamp": [0.0, 0.0, 0.5, 0.5, 1.0],
                "class_id": [-1, 3, -1, 3, -1],
            }
        )

        tb = resolve_time_base(_trajectory([0.0, 0.5, 1.0]), objects_df=objects)

        assert tb.source == SOURCE_HEARTBEAT
        assert tb.duration_s == pytest.approx(1.5)

    def test_objects_without_heartbeat_fall_through(self) -> None:
        objects = pd.DataFrame({"frame": [0, 1], "timestamp": [0.0, 1.0], "class_id": [2, 2]})

        tb = resolve_time_base(_trajectory(np.arange(10) / 10.0), objects_df=objects)

        assert tb.source == SOURCE_TRAJECTORY

    def test_ledger_wins_over_trajectory(self) -> None:
        # Processing clock in the trajectory says 1 fps; capture says 20 fps.
        df = _trajectory(np.arange(10) * 1.0, frames=np.arange(1, 11))
        ledger = _ledger_rows(list(100.0 + np.arange(10) / 20.0))

        tb = resolve_time_base(df, ledger=ledger, fallback_fps=30.0)

        assert tb.source == SOURCE_LEDGER
        assert tb.fps_video == pytest.approx(20.0)
        assert tb.duration_s == pytest.approx(10 / 20.0)
        # Relative to the first capture (the anchor's t0_perf).
        assert tb.t_first == pytest.approx(0.0)

    def test_ledger_sampling_rate_follows_the_analysed_frames(self) -> None:
        df = _trajectory(np.arange(5) * 1.0, frames=[2, 4, 6, 8, 10])
        ledger = _ledger_rows(list(np.arange(10) / 10.0), first_frame=1, analysis_every=2)

        tb = resolve_time_base(df, ledger=ledger)

        assert tb.fps_video == pytest.approx(10.0)
        assert tb.fps_sampling == pytest.approx(5.0)

    def test_ledger_dataframe_is_accepted(self) -> None:
        ledger = pd.DataFrame(_ledger_rows(list(np.arange(10) / 10.0)))

        tb = resolve_time_base(_trajectory([0.0]), ledger=ledger)

        assert tb.source == SOURCE_LEDGER
        assert tb.duration_s == pytest.approx(1.0)

    def test_ledger_without_timestamps_falls_through(self) -> None:
        ledger = _ledger_rows([None, None])

        tb = resolve_time_base(_trajectory(np.arange(10) / 10.0), ledger=ledger)

        assert tb.source == SOURCE_TRAJECTORY

    def test_time_base_is_frozen(self) -> None:
        tb = resolve_time_base(_trajectory(np.arange(10) / 10.0))

        with pytest.raises(AttributeError):
            tb.duration_s = 1.0  # type: ignore[misc]
        assert isinstance(tb, TimeBase)


class TestRetimeFromLedger:
    def test_replaces_only_the_time_axis(self) -> None:
        df = _trajectory([50.0, 50.7, 51.9], frames=[1, 2, 3])
        rows = _ledger_rows([10.0, 10.1, 10.2])
        anchor = {"t0_perf": 10.0, "t0_wall": 1_700_000_010.0}

        out = retime_from_ledger(df, rows, anchor)

        assert out["timestamp"].tolist() == pytest.approx([0.0, 0.1, 0.2])
        pd.testing.assert_frame_equal(out.drop(columns="timestamp"), df.drop(columns="timestamp"))
        # The caller's frame (the Parquet in memory) is untouched.
        assert df["timestamp"].tolist() == [50.0, 50.7, 51.9]
        assert out.attrs.get(TIME_WARNINGS_ATTR, []) == []

    def test_anchor_t0_defines_the_zero(self) -> None:
        df = _trajectory([0.0, 1.0], frames=[2, 3])
        rows = _ledger_rows([10.0, 10.1, 10.2])

        out = retime_from_ledger(df, rows, {"t0_perf": 9.5})

        assert out["timestamp"].tolist() == pytest.approx([0.6, 0.7])

    def test_missing_anchor_uses_first_capture(self) -> None:
        df = _trajectory([0.0, 1.0], frames=[2, 3])
        rows = _ledger_rows([10.0, 10.1, 10.2])

        out = retime_from_ledger(df, rows, {})

        assert out["timestamp"].tolist() == pytest.approx([0.1, 0.2])

    def test_duplicate_frames_of_two_tracks_share_the_capture_time(self) -> None:
        df = _trajectory([7.0, 7.0, 9.0, 9.0], frames=[1, 1, 2, 2], track_ids=[1, 2, 1, 2])
        rows = _ledger_rows([0.0, 0.25])

        out = retime_from_ledger(df, rows, {"t0_perf": 0.0})

        assert out["timestamp"].tolist() == pytest.approx([0.0, 0.0, 0.25, 0.25])

    def test_without_ledger_returns_the_frame_intact_with_a_warning(self) -> None:
        df = _trajectory([0.0, 1.0])

        out = retime_from_ledger(df, [], {})

        pd.testing.assert_frame_equal(out, df)
        assert out.attrs[TIME_WARNINGS_ATTR]

    def test_unmatched_frame_keeps_one_clock(self) -> None:
        """Mixing capture and processing clocks would be worse than either."""
        df = _trajectory([0.0, 1.0, 2.0], frames=[1, 2, 99])
        rows = _ledger_rows([0.0, 0.1, 0.2])

        out = retime_from_ledger(df, rows, {"t0_perf": 0.0})

        assert out["timestamp"].tolist() == [0.0, 1.0, 2.0]
        assert out.attrs[TIME_WARNINGS_ATTR]

    def test_frame_without_capture_time_keeps_one_clock(self) -> None:
        df = _trajectory([0.0, 1.0], frames=[1, 2])
        rows = _ledger_rows([0.0, None])

        out = retime_from_ledger(df, rows, {"t0_perf": 0.0})

        assert out["timestamp"].tolist() == [0.0, 1.0]
        assert out.attrs[TIME_WARNINGS_ATTR]

    def test_without_frame_column_returns_intact(self) -> None:
        df = pd.DataFrame({"timestamp": [0.0, 1.0]})

        out = retime_from_ledger(df, _ledger_rows([0.0, 0.1]), {})

        pd.testing.assert_frame_equal(out, df)
        assert out.attrs[TIME_WARNINGS_ATTR]

    def test_retimed_frame_resolves_to_the_capture_rate(self) -> None:
        df = _trajectory(np.arange(10) * 1.0, frames=np.arange(1, 11))
        rows = _ledger_rows(list(np.arange(10) / 20.0))

        out = retime_from_ledger(df, rows, {"t0_perf": 0.0})

        assert resolve_time_base(out).fps_sampling == pytest.approx(20.0)
