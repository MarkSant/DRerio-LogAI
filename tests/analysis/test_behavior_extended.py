"""Extended unit tests for analysis/behavior.py."""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.behavior import BehavioralAnalyzer, Episode


class DummyBehaviorAnalyzer(BehavioralAnalyzer):
    def calculate_freezing(self, *args, **kwargs):
        return []

    def calculate_burst_swimming(self, *args, **kwargs):
        return []

    def calculate_locomotion(self, *args, **kwargs):
        return {}

    def calculate_total_distance(self, *args, **kwargs):
        return 0.0

    def calculate_velocity_timeseries(self, *args, **kwargs):
        return pd.Series(dtype=float)

    def detect_freezing_episodes(self, *args, **kwargs):
        return []

    def get_angular_velocity(self, *args, **kwargs):
        return pd.Series(dtype=float)

    def get_thigmotaxis_timeseries(self, *args, **kwargs):
        return pd.Series(dtype=bool)

    def get_tortuosity(self, *args, **kwargs):
        return 1.0


class TestBehaviorExtended:
    def test_episode_typed_dict(self):
        ep: Episode = {
            "start_time": pd.Timedelta(seconds=1),
            "end_time": pd.Timedelta(seconds=5),
            "duration": 4.0,
            "track_id": 1,
        }
        assert ep["duration"] == 4.0
        assert ep["track_id"] == 1

    def test_polyorder_greater_equal_window_raises(self):
        df = pd.DataFrame(
            {
                "timestamp": [0.0, 0.033, 0.066],
                "x_center_px": [10.0, 11.0, 12.0],
                "y_center_px": [20.0, 21.0, 22.0],
                "x1": [5, 6, 7],
                "y1": [15, 16, 17],
                "x2": [15, 16, 17],
                "y2": [25, 26, 27],
            }
        )
        arena = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

        with pytest.raises(ValueError, match="polyorder must be less than window_length"):
            DummyBehaviorAnalyzer(
                trajectory_df=df,
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=480,
                arena_polygon_px=arena,
                window_length=3,
                polyorder=3,
            )

    def test_behavior_analyzer_valid_init(self):
        df = pd.DataFrame(
            {
                "timestamp": [0.0, 0.033, 0.066, 0.1, 0.133, 0.166, 0.2],
                "x_center_px": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
                "y_center_px": [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0],
                "x1": [5, 6, 7, 8, 9, 10, 11],
                "y1": [15, 16, 17, 18, 19, 20, 21],
                "x2": [15, 16, 17, 18, 19, 20, 21],
                "y2": [25, 26, 27, 28, 29, 30, 31],
            }
        )
        arena = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

        analyzer = DummyBehaviorAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=arena,
            window_length=5,
            polyorder=2,
            fps=30.0,
        )
        assert analyzer._pixelcm_x == 10.0
        assert analyzer._pixelcm_y == 10.0
        assert analyzer._video_height_px == 480
        assert analyzer.fps == 30.0
        assert analyzer.is_multi_track is False
        assert isinstance(analyzer.trajectory_data, pd.DataFrame)

    def test_behavior_analyzer_track_keys_single(self):
        df = pd.DataFrame(
            {
                "timestamp": [0.0, 0.033, 0.066, 0.1, 0.133, 0.166, 0.2],
                "x_center_px": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
                "y_center_px": [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0],
                "x1": [5, 6, 7, 8, 9, 10, 11],
                "y1": [15, 16, 17, 18, 19, 20, 21],
                "x2": [15, 16, 17, 18, 19, 20, 21],
                "y2": [25, 26, 27, 28, 29, 30, 31],
            }
        )
        arena = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

        analyzer = DummyBehaviorAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=480,
            arena_polygon_px=arena,
            window_length=5,
            polyorder=2,
            fps=30.0,
        )
        assert analyzer._track_keys == []


class TestBehaviorExtended2:
    def test_episode_typed_dict(self):
        ep: Episode = {
            "start_time": pd.Timedelta(seconds=1),
            "end_time": pd.Timedelta(seconds=5),
            "duration": 4.0,
            "track_id": 1,
        }
        assert ep["duration"] == 4.0
        assert ep["track_id"] == 1
        assert "start_time" in ep
        assert "end_time" in ep

    def test_episode_without_track_id(self):
        ep: Episode = {
            "start_time": 0.0,
            "end_time": 2.5,
            "duration": 2.5,
        }
        assert ep["duration"] == 2.5
        assert "track_id" not in ep

    def test_episode_zero_duration(self):
        ep: Episode = {
            "start_time": 10.0,
            "end_time": 10.0,
            "duration": 0.0,
        }
        assert ep["duration"] == 0.0
