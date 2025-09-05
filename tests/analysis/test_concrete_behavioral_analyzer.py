import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer


@pytest.fixture
def straight_line_trajectory():
    """
    Generates a simple, 10-second straight-line trajectory for testing.
    The trajectory moves from (10, 20) to (110, 20) in pixels.
    With a 10px/cm ratio, this is a 10cm straight line.
    """
    timestamps = np.linspace(0, 10, 101)  # 101 points over 10 seconds
    x_coords_px = np.linspace(10, 110, 101)
    y_coords_px = np.full_like(x_coords_px, 20)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_coords_px,
            "y_center_px": y_coords_px,
            # Dummy bbox data, not used for distance/freezing
            "x1": x_coords_px - 1,
            "y1": y_coords_px - 1,
            "x2": x_coords_px + 1,
            "y2": y_coords_px + 1,
        }
    )

    # Metadata for the analyzer
    metadata = {
        "trajectory_df": df,
        "pixelcm_x": 10.0,  # 10 pixels per cm
        "pixelcm_y": 10.0,
        "video_height_px": 200,
        "arena_polygon_px": [(0, 0), (200, 0), (200, 200), (0, 200)],
        # Use a window_length smaller than the number of points
        "window_length": 5,
        "polyorder": 2,
    }
    return metadata


def test_calculate_total_distance_straight_line(straight_line_trajectory):
    """
    Tests that the total distance for a simple straight-line trajectory is
    calculated correctly.
    """
    analyzer = ConcreteBehavioralAnalyzer(**straight_line_trajectory)

    # The trajectory moves 100 pixels horizontally.
    # With a ratio of 10 px/cm, the distance should be 10 cm.
    expected_distance = 10.0
    # Smoothing a straight line should still result in a straight line,
    # so the distance should be very close to the expectation.
    calculated_distance = analyzer.calculate_total_distance()

    assert calculated_distance == pytest.approx(expected_distance, rel=1e-3)


@pytest.fixture
def freezing_trajectory():
    """
    Generates a trajectory with a clear 5-second freezing episode.
    - t=0-2s: Moving
    - t=2-7s: Stationary (freezing)
    - t=7-10s: Moving again
    """
    timestamps = np.linspace(0, 10, 101)
    x_coords_px = np.zeros_like(timestamps)
    y_coords_px = np.zeros_like(timestamps)

    # Before t=2s
    move1_mask = timestamps < 2
    x_coords_px[move1_mask] = np.linspace(0, 20, np.sum(move1_mask))

    # Between t=2s and t=7s (stationary at 20px)
    freeze_mask = (timestamps >= 2) & (timestamps <= 7)
    x_coords_px[freeze_mask] = 20

    # After t=7s
    move2_mask = timestamps > 7
    x_coords_px[move2_mask] = np.linspace(20, 40, np.sum(move2_mask))

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_coords_px,
            "y_center_px": y_coords_px,
            "x1": x_coords_px - 1, "y1": y_coords_px - 1,
            "x2": x_coords_px + 1, "y2": y_coords_px + 1,
        }
    )
    metadata = {
        "trajectory_df": df,
        "pixelcm_x": 10.0, "pixelcm_y": 10.0,
        "video_height_px": 200,
        "arena_polygon_px": [(0, 0), (200, 0), (200, 200), (0, 200)],
        "window_length": 5, "polyorder": 2,
    }
    return metadata


def test_detect_freezing_episodes(freezing_trajectory):
    """
    Tests that a clear freezing episode is correctly detected.
    """
    analyzer = ConcreteBehavioralAnalyzer(**freezing_trajectory)

    # Velocity threshold in cm/s. The freezing part has 0 velocity.
    vel_threshold = 0.1
    # Minimum duration for an episode to be counted.
    min_duration = 2.0  # seconds

    episodes = analyzer.detect_freezing_episodes(vel_threshold, min_duration)

    # We expect to find exactly one episode
    assert len(episodes) == 1
    episode = episodes[0]

    # The episode should last approximately 4.9 seconds. The velocity calculation
    # using .diff() means the first point with zero velocity is at t=2.1,
    # and the last is at t=7.0.
    assert episode["duration"] == pytest.approx(4.9, abs=0.1)
    # Check start and end times, accounting for the diff() offset.
    assert episode["start_time"] == pytest.approx(2.1, abs=0.1)
    assert episode["end_time"] == pytest.approx(7.0, abs=0.1)
