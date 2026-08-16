"""
Extended unit tests for ConcreteBehavioralAnalyzer in analysis/behavior.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer


@pytest.fixture
def sample_trajectory_data() -> pd.DataFrame:
    """Generate a clean synthetic trajectory DataFrame with 60 frames (2 seconds at 30 fps)."""
    n = 60
    timestamps = pd.timedelta_range(start="0s", periods=n, freq="33.333333ms")
    # Linear movement along X
    x = np.linspace(100.0, 400.0, n)
    y = np.full(n, 200.0)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x,
            "y_center_px": y,
            "x1": x - 10.0,
            "y1": y - 10.0,
            "x2": x + 10.0,
            "y2": y + 10.0,
        },
        index=timestamps,
    )
    return df


@pytest.fixture
def arena_polygon() -> list[list[float]]:
    """Simple 500x500 rectangular arena polygon."""
    return [[0.0, 0.0], [500.0, 0.0], [500.0, 500.0], [0.0, 500.0]]


class TestConcreteBehavioralAnalyzerExtended:
    """Test initialization, thigmotaxis, geotaxis, inactivity, speed bursts, and tortuosity."""

    def test_init_polyorder_greater_equal_window_raises(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        with pytest.raises(ValueError, match="polyorder must be less than window_length"):
            ConcreteBehavioralAnalyzer(
                sample_trajectory_data,
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=500,
                arena_polygon_px=arena_polygon,
                window_length=5,
                polyorder=5,
            )

    def test_thigmotaxis_index_methods(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )

        avg_dist = analyzer.calculate_thigmotaxis_index(method="average_distance")
        assert isinstance(avg_dist, float)
        assert avg_dist > 0

        pct_near = analyzer.calculate_thigmotaxis_index(
            method="time_near_wall", distance_threshold=25.0
        )
        assert isinstance(pct_near, float)
        assert 0.0 <= pct_near <= 100.0

        # Missing threshold for time_near_wall
        with pytest.raises(ValueError, match="'distance_threshold' is required"):
            analyzer.calculate_thigmotaxis_index(method="time_near_wall")

        # Unsupported method
        with pytest.raises(ValueError, match="Unsupported method"):
            analyzer.calculate_thigmotaxis_index(method="invalid_method")

    def test_geotaxis_index_methods(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )

        avg_bottom = analyzer.calculate_geotaxis_index(method="average_distance")
        assert isinstance(avg_bottom, float)
        assert avg_bottom >= 0

        pct_bottom = analyzer.calculate_geotaxis_index(
            method="time_near_bottom", distance_threshold=50.0
        )
        assert isinstance(pct_bottom, float)
        assert 0.0 <= pct_bottom <= 100.0

        zones = analyzer.calculate_geotaxis_index(method="zone_time", num_zones=3)
        assert isinstance(zones, dict)
        assert "bottom_zones_pct" in zones
        assert "zone_0_pct" in zones
        assert "zone_1_pct" in zones
        assert "zone_2_pct" in zones

        # Unsupported method
        with pytest.raises(ValueError, match="Unknown method"):
            analyzer.calculate_geotaxis_index(method="nonexistent_method")

    def test_tortuosity_sliding_window_raises(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )
        with pytest.raises(NotImplementedError):
            analyzer.get_tortuosity(window_size=1.0)

    def test_tortuosity_straight_line(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )
        tort = analyzer.get_tortuosity()
        # Straight line tortuosity is approximately 1.0
        assert pytest.approx(tort, rel=0.05) == 1.0

    def test_speed_bursts_and_inactivity(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )

        bursts = analyzer.calculate_speed_bursts(threshold_cm_s=10.0, min_duration=0.1)
        assert "count" in bursts
        assert "total_duration_s" in bursts
        assert "episodes" in bursts

        inactivity = analyzer.calculate_inactivity_periods(
            velocity_threshold_cm_s=1.0, min_duration=0.5
        )
        assert "count" in inactivity
        assert "total_duration_s" in inactivity
        assert "percentage_of_recording" in inactivity

    def test_angular_velocity_stats_and_sharp_turns(
        self, sample_trajectory_data: pd.DataFrame, arena_polygon: list[list[float]]
    ):
        analyzer = ConcreteBehavioralAnalyzer(
            sample_trajectory_data,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=500,
            arena_polygon_px=arena_polygon,
        )

        stats = analyzer.get_angular_velocity_stats()
        assert "mean" in stats
        assert "median" in stats
        assert "max" in stats
        assert "std_dev" in stats

        turns = analyzer.calculate_sharp_turns(threshold_deg_s=45.0)
        assert "sharp_turns_count" in turns
        assert "sharp_turns_per_minute" in turns
