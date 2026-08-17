"""Extended unit tests for analysis/behavior.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer, Episode


class TestBehavioralAnalyzerExtended:
    """Test Episode TypedDict and ConcreteBehavioralAnalyzer calculations."""

    def test_episode_typed_dict(self):
        ep: Episode = {
            "start_time": pd.Timedelta(seconds=1.0),
            "end_time": pd.Timedelta(seconds=4.0),
            "duration": 3.0,
            "track_id": 1,
        }
        assert ep["duration"] == 3.0
        assert ep["track_id"] == 1

    def test_analyzer_init_and_tortuosity(self):
        # Create a simple 10-frame straight line trajectory (0 to 9 on X)
        timestamps = pd.to_timedelta(np.arange(10) * 0.1, unit="s")
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": np.linspace(10, 100, 10),
                "y_center_px": np.full(10, 50.0),
                "x1": np.linspace(5, 95, 10),
                "y1": np.full(10, 45.0),
                "x2": np.linspace(15, 105, 10),
                "y2": np.full(10, 55.0),
            }
        )
        arena = [(0, 0), (0, 100), (200, 100), (200, 0)]

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
            arena_polygon_px=arena,
            fps=10.0,
            window_length=5,
            polyorder=2,
        )

        # Tortuosity of straight line is ~1.0
        tort = analyzer.get_tortuosity()
        assert pytest.approx(float(tort), rel=1e-2) == 1.0

        # Thigmotaxis timeseries should return non-empty series
        thigmo = analyzer.get_thigmotaxis_timeseries()
        assert len(thigmo) == 10
        assert not thigmo.isna().all()

        # Angular velocity stats
        av_stats = analyzer.get_angular_velocity_stats()
        assert "mean" in av_stats
        assert "median" in av_stats
        assert "max" in av_stats
        assert "std_dev" in av_stats

    def test_analyzer_polyorder_validation(self):
        timestamps = pd.to_timedelta(np.arange(5) * 0.1, unit="s")
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": np.arange(5),
                "y_center_px": np.arange(5),
                "x1": np.arange(5),
                "y1": np.arange(5),
                "x2": np.arange(5),
                "y2": np.arange(5),
            }
        )
        arena = [(0, 0), (0, 10), (10, 10), (10, 0)]

        # polyorder (3) >= window_length (3) must raise ValueError
        with pytest.raises(ValueError, match="polyorder must be less than window_length"):
            ConcreteBehavioralAnalyzer(
                trajectory_df=df,
                pixelcm_x=1.0,
                pixelcm_y=1.0,
                video_height_px=10,
                arena_polygon_px=arena,
                window_length=3,
                polyorder=3,
            )
