# -*- coding: utf-8 -*-
"""
Tests for the ConcreteBehavioralAnalyzer class.
"""

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer


@pytest.fixture
def sample_trajectory_data():
    """
    Provides a sample trajectory dataset for testing.
    """
    timestamps = np.linspace(0, 10, 101)
    px = np.linspace(10, 110, 101)
    py = np.linspace(20, 220, 101)
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": px,
            "y_center_px": py,
            "x1": px - 1,
            "y1": py - 1,
            "x2": px + 1,
            "y2": py + 1,
        }
    )
    return {
        "trajectory_df": df,
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 240,
        "arena_polygon_px": [(0, 0), (120, 0), (120, 240), (0, 240)],
        "fps": 10,
        "window_length": 7,
        "polyorder": 3,
    }


def test_get_tortuosity_straight_line(sample_trajectory_data):
    """Tests tortuosity for a straight line trajectory."""
    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    # For a straight line, tortuosity should be 1.0
    assert np.isclose(analyzer.get_tortuosity(), 1.0)


def test_get_tortuosity_zero_distance(sample_trajectory_data):
    """Tests tortuosity when start and end points are the same."""
    # Create a trajectory that starts and ends at the same point but moves in between
    timestamps = [0, 1, 2]
    px = np.array([10, 50, 10])
    py = np.array([20, 60, 20])
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": px,
            "y_center_px": py,
            "x1": px - 1,
            "y1": py - 1,
            "x2": px + 1,
            "y2": py + 1,
        }
    )
    sample_trajectory_data["trajectory_df"] = df
    # Disable smoothing to test the zero distance case precisely
    sample_trajectory_data["window_length"] = 1
    sample_trajectory_data["polyorder"] = 0

    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    # When start and end points are the same, and path was traveled, tortuosity is nan.
    assert np.isnan(analyzer.get_tortuosity())


def test_get_angular_velocity_non_uniform_timestamps(sample_trajectory_data):
    """Tests angular velocity with non-uniform time intervals."""
    # Create a trajectory with non-uniform timestamps
    timestamps = [0, 1, 3, 6]  # dt = 1, 2, 3
    px = np.array([10, 20, 20, 20])
    py = np.array([10, 10, 20, 20])  # 90 degree turn (clockwise)
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": px,
            "y_center_px": py,
            "x1": px - 1,
            "y1": py - 1,
            "x2": px + 1,
            "y2": py + 1,
        }
    )
    sample_trajectory_data["trajectory_df"] = df
    # Disable smoothing for predictable angular velocity
    sample_trajectory_data["window_length"] = 1
    sample_trajectory_data["polyorder"] = 0
    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    angular_velocity = analyzer.get_angular_velocity()

    # The turn happens at index 2 (time = 3s)
    # The angle changes from 0 to -90 degrees (clockwise).
    # The time difference is 2s (from t=1 to t=3).
    # Expected angular velocity is approx -90 / 2 = -45 deg/s.
    assert np.isclose(angular_velocity.iloc[2], -45.0, atol=1e-1)


def test_detect_freezing_episodes_absolute(sample_trajectory_data):
    """Tests freezing detection with an absolute threshold."""
    timestamps = np.linspace(0, 10, 101)
    px = np.array([10] * 50 + list(np.linspace(10, 20, 51)))
    py = np.array([20] * 50 + list(np.linspace(20, 30, 51)))
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": px,
            "y_center_px": py,
            "x1": px - 1,
            "y1": py - 1,
            "x2": px + 1,
            "y2": py + 1,
        }
    )
    sample_trajectory_data["trajectory_df"] = df
    sample_trajectory_data["window_length"] = 1
    sample_trajectory_data["polyorder"] = 0
    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)

    # The first 50 points are stationary. This corresponds to 49 velocity points.
    # The duration of freezing is 4.8s (t_49 - t_1)
    episodes = analyzer.detect_freezing_episodes(
        min_duration=1, vel_threshold=0.1, threshold_method="absolute"
    )
    assert len(episodes) == 1
    assert np.isclose(episodes[0]["duration"], 4.8, atol=0.1)


def test_detect_freezing_episodes_relative(sample_trajectory_data):
    """Tests freezing detection with a relative threshold."""
    timestamps = np.linspace(0, 10, 101)
    px = np.array([10] * 50 + list(np.linspace(10, 100, 51)))
    py = np.array([20] * 50 + list(np.linspace(20, 100, 51)))
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": px,
            "y_center_px": py,
            "x1": px - 1,
            "y1": py - 1,
            "x2": px + 1,
            "y2": py + 1,
        }
    )
    sample_trajectory_data["trajectory_df"] = df
    sample_trajectory_data["window_length"] = 1
    sample_trajectory_data["polyorder"] = 0
    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)

    # The first 50 points are stationary. This corresponds to 49 velocity points.
    # The duration of freezing is 4.8s (t_49 - t_1)
    episodes = analyzer.detect_freezing_episodes(
        min_duration=1, threshold_method="relative", quantile=0.1
    )
    assert len(episodes) == 1
    assert np.isclose(episodes[0]["duration"], 4.8, atol=0.1)


def test_detect_freezing_episodes_value_error(sample_trajectory_data):
    """Tests that a ValueError is raised for unknown method."""
    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    with pytest.raises(ValueError, match="Unknown threshold_method"):
        analyzer.detect_freezing_episodes(min_duration=1, threshold_method="unknown")

    with pytest.raises(
        ValueError, match="vel_threshold must be set for 'absolute' method."
    ):
        analyzer.detect_freezing_episodes(min_duration=1, threshold_method="absolute")


def test_calculate_speed_bursts(sample_trajectory_data):
    """Ensures speed burst detection returns the expected episode."""
    timestamps = np.linspace(0, 10, 101)
    x_cm = np.zeros_like(timestamps)

    for idx, t in enumerate(timestamps):
        if t <= 3:
            x_cm[idx] = t * 1.0  # 1 cm/s baseline
        elif t <= 5:
            x_cm[idx] = 3 + (t - 3) * 10.0  # 10 cm/s burst
        else:
            x_cm[idx] = 23 + (t - 5) * 1.0  # back to baseline

    x_px = x_cm * sample_trajectory_data["pixelcm_x"]
    y_px = np.zeros_like(x_px)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_px,
            "y_center_px": y_px,
            "x1": x_px - 1,
            "y1": y_px - 1,
            "x2": x_px + 1,
            "y2": y_px + 1,
        }
    )

    sample_trajectory_data.update({
        "trajectory_df": df,
        "window_length": 1,
        "polyorder": 0,
    })

    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    result = analyzer.calculate_speed_bursts(threshold_cm_s=8.0, min_duration=1.0)

    assert result["count"] == 1
    assert result["threshold_cm_s"] == pytest.approx(8.0)
    assert result["total_duration_s"] == pytest.approx(2.0, abs=0.2)


def test_calculate_inactivity_periods(sample_trajectory_data):
    """Validates inactivity detection using a long stationary segment."""
    timestamps = np.linspace(0, 10, 101)
    x_cm = np.concatenate([
        np.zeros(31),  # 0-3s stationary
        np.linspace(0, 10, 70),
    ])
    x_px = x_cm * sample_trajectory_data["pixelcm_x"]
    y_px = np.zeros_like(x_px)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_px,
            "y_center_px": y_px,
            "x1": x_px - 1,
            "y1": y_px - 1,
            "x2": x_px + 1,
            "y2": y_px + 1,
        }
    )

    sample_trajectory_data.update({
        "trajectory_df": df,
        "window_length": 1,
        "polyorder": 0,
    })

    analyzer = ConcreteBehavioralAnalyzer(**sample_trajectory_data)
    result = analyzer.calculate_inactivity_periods(
        velocity_threshold_cm_s=0.2, min_duration=2.0
    )

    assert result["count"] == 1
    assert result["total_duration_s"] == pytest.approx(3.0, abs=0.2)
    assert result["percentage_of_recording"] == pytest.approx(30.0, abs=2.0)
