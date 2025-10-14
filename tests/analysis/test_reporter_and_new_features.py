import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.project_manager import ProjectManager


@pytest.fixture
def sharp_turn_trajectory():
    """
    Generates a trajectory with a sharp 90-degree turn.
    - t=0-5s: Moves straight along the x-axis.
    - t=5-10s: Moves straight along the y-axis.
    This creates a 90-degree turn at t=5s.
    """
    timestamps = pd.to_datetime(np.linspace(0, 10, 101), unit="s")
    x_coords_px = np.zeros_like(timestamps, dtype=float)
    y_coords_px = np.zeros_like(timestamps, dtype=float)

    # 0-5s: move 50px in x
    move1_mask = timestamps <= pd.Timestamp("1970-01-01 00:00:05")
    x_coords_px[move1_mask] = np.linspace(0, 50, np.sum(move1_mask))
    y_coords_px[move1_mask] = 0

    # 5-10s: move 50px in y
    move2_mask = timestamps > pd.Timestamp("1970-01-01 00:00:05")
    x_coords_px[move2_mask] = 50
    y_coords_px[move2_mask] = np.linspace(0, 50, np.sum(move2_mask))

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_coords_px,
            "y_center_px": y_coords_px,
            "x1": x_coords_px - 1,
            "y1": y_coords_px - 1,
            "x2": x_coords_px + 1,
            "y2": y_coords_px + 1,
        }
    )
    metadata = {
        "trajectory_df": df,
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 200,
        "arena_polygon_px": [(0, 0), (200, 0), (200, 200), (0, 200)],
        "window_length": 5,
        "polyorder": 2,
        "fps": 10.0,
    }
    return metadata


def test_calculate_sharp_turns(sharp_turn_trajectory):
    """
    Tests that the sharp turn calculation correctly identifies a sharp turn.
    """
    # Disable jitter filtering for this legacy test (threshold = 0 disables it)
    sharp_turn_trajectory["min_displacement_threshold_cm"] = 0.0
    sharp_turn_trajectory["angle_calculation_window"] = 1
    sharp_turn_trajectory["angular_velocity_smoothing_window"] = 1

    analyzer = ConcreteBehavioralAnalyzer(**sharp_turn_trajectory)

    # With the new robust angular velocity algorithm, the calculated values differ
    # from the old implementation. The maximum angular velocity is around 260 deg/s.
    # A threshold of 200 deg/s should catch this turn.
    results = analyzer.calculate_sharp_turns(threshold_deg_s=200.0)

    assert results["sharp_turns_count"] >= 1, "Should detect at least one sharp turn"
    # At least 1 turn in 10s = 6+ turns/min
    assert results["sharp_turns_per_minute"] >= 6.0


@pytest.fixture
def roi_crossing_trajectory():
    """
    Generates a trajectory that enters and exits a specific ROI.
    - t=0-2.5s: Outside ROI
    - t=2.5-7.5s: Inside ROI
    - t=7.5-10s: Outside ROI
    The ROI is a box from (2.5, 2.5) to (7.5, 7.5) cm.
    """
    timestamps = pd.to_datetime(np.linspace(0, 10, 101), unit="s")
    x_coords_px = np.linspace(0, 100, 101)  # Moves 10cm in x
    # Y in pixels moves from 180 down to 120.
    # With height=200, pixelcm=10, this is y_cm=(200-180)/10=2 to y_cm=(200-120)/10=8
    # This ensures it crosses the ROI defined from y_cm=2.5 to 7.5
    y_coords_px = np.linspace(180, 120, 101)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_coords_px,
            "y_center_px": y_coords_px,
            "x1": x_coords_px - 1,
            "y1": y_coords_px - 1,
            "x2": x_coords_px + 1,
            "y2": y_coords_px + 1,
        }
    )

    # ROI geometry is in CM
    roi_geom = box(2.5, 2.5, 7.5, 7.5)
    test_roi = ROI(name="TestZone", geometry=roi_geom)

    metadata = {
        "trajectory_df": df,
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 200,
        "arena_polygon_px": [(0, 0), (200, 0), (200, 200), (0, 200)],
        "rois": [test_roi],
        "fps": 10.0,
    }
    return metadata


def test_get_distance_in_roi(roi_crossing_trajectory):
    """
    Tests that distance traveled *inside* an ROI is calculated correctly.
    """
    b_analyzer = ConcreteBehavioralAnalyzer(
        **{k: v for k, v in roi_crossing_trajectory.items() if k != "rois"}
    )
    r_analyzer = ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=roi_crossing_trajectory["rois"],
        inclusion_rule="centroid_in",
    )

    distances = r_analyzer.get_distance_in_rois()

    # The animal is inside the ROI between t=2.5s and t=7.5s (x_cm from 2.5 to 7.5).
    # This is a distance of 5cm in x and 5cm in y.
    # Distance = sqrt(5^2 + 5^2) = 7.07 cm.
    expected_distance_in_roi = np.sqrt(5**2 + 5**2)

    # The calculated distance will be slightly different due to smoothing.
    assert distances["TestZone"] == pytest.approx(expected_distance_in_roi, rel=0.2)


def test_get_event_log(roi_crossing_trajectory):
    """
    Tests that the event log correctly identifies entry and exit events.
    """
    b_analyzer = ConcreteBehavioralAnalyzer(
        **{k: v for k, v in roi_crossing_trajectory.items() if k != "rois"}
    )
    r_analyzer = ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=roi_crossing_trajectory["rois"],
        flutter_n_frames=3,
        inclusion_rule="centroid_in",
    )

    event_log = r_analyzer.get_event_log()

    assert len(event_log) == 2
    assert event_log.iloc[0]["event"] == "enter"
    assert event_log.iloc[0]["roi_name"] == "TestZone"
    assert event_log.iloc[1]["event"] == "exit"
    assert event_log.iloc[1]["roi_name"] == "TestZone"

    entry_time = event_log.iloc[0]["timestamp"].total_seconds()
    exit_time = event_log.iloc[1]["timestamp"].total_seconds()

    # With flutter filter of 3, entry is confirmed at t=2.7s, exit at t=7.7s
    assert entry_time == pytest.approx(2.7, abs=0.1)
    assert exit_time == pytest.approx(7.7, abs=0.1)


def test_project_manager_metadata_fallback():
    """
    Tests that the ProjectManager can extract metadata from a filename
    if it's not present in the metadata.csv file.
    """
    pm = ProjectManager()
    # Simulate that metadata.csv is empty or doesn't contain the ID
    pm.metadata = pd.DataFrame(columns=["experiment_id"])

    experiment_id = "D1_GControl_S3"
    metadata = pm.get_metadata_for_experiment(experiment_id)

    assert metadata is not None
    assert metadata["day"] == 1
    assert metadata["group"] == "Control"
    assert metadata["subject"] == 3

    # Test with a more complex group name
    experiment_id_2 = "D12_GGroup Name with spaces_S15"
    metadata_2 = pm.get_metadata_for_experiment(experiment_id_2)
    assert metadata_2["day"] == 12
    assert metadata_2["group"] == "Group Name with spaces"
    assert metadata_2["subject"] == 15

    # Test failure case
    experiment_id_3 = "invalid_filename"
    metadata_3 = pm.get_metadata_for_experiment(experiment_id_3)
    assert metadata_3 == {}
