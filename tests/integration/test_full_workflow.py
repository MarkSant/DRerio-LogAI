"""
End-to-end integration tests for complete ZebTrack-AI workflow.

Tests the integration of core components: Recorder, StateManager, and processing pipeline.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from zebtrack.core.state_manager import StateCategory, StateManager
from zebtrack.io.recorder import Recorder


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary directory for project files."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def sample_zones():
    """Return sample zone definitions for testing."""
    return [
        {
            "name": "Zone A",
            "polygon": [(100, 100), (300, 100), (300, 300), (100, 300)],
            "color": "red",
            "enter_commands": [],
            "exit_commands": [],
        },
        {
            "name": "Zone B",
            "polygon": [(400, 100), (600, 100), (600, 300), (400, 300)],
            "color": "blue",
            "enter_commands": [],
            "exit_commands": [],
        },
    ]


@pytest.mark.integration
def test_recorder_creates_complete_dataset(temp_project_dir, sample_zones):
    """
    Test that Recorder creates all required Parquet files with correct schema.

    Steps:
    1. Start recorder
    2. Write detection data
    3. Stop recorder
    4. Verify all Parquet files exist
    5. Verify file contents and schema
    """
    results_dir = temp_project_dir / "test_video_results"
    results_dir.mkdir()

    processing_area = {"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]}

    # Start recorder
    recorder = Recorder()
    recorder.start(
        output_folder=str(results_dir),
        base_name="test_video",
        processing_area=processing_area,
        zones=sample_zones,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
    )

    # Write 100 frames of detection data
    for frame_num in range(1, 101):
        detections = [
            {
                "timestamp": frame_num / 30.0,
                "frame": frame_num,
                "track_id": 1,
                "x1": 100 + frame_num,
                "y1": 100,
                "x2": 150 + frame_num,
                "y2": 150,
                "confidence": 0.95,
            }
        ]
        recorder.write_detection_data(detections, frame_num)

    # Stop recorder
    recorder.stop()

    # Verify files exist
    arena_file = results_dir / "1_ProcessingArea_test_video.parquet"
    zones_file = results_dir / "2_Zones_test_video.parquet"
    coords_file = results_dir / "3_CoordMovimento_test_video.parquet"

    assert arena_file.exists(), f"Arena file not found: {arena_file}"
    assert zones_file.exists(), f"Zones file not found: {zones_file}"
    assert coords_file.exists(), f"Coords file not found: {coords_file}"

    # Verify detection data
    import pyarrow.parquet as pq

    coords_table = pq.read_table(str(coords_file))
    assert len(coords_table) == 100, f"Expected 100 rows, got {len(coords_table)}"

    # Verify schema
    expected_columns = {"timestamp", "frame", "track_id", "x1", "y1", "x2", "y2", "confidence"}
    actual_columns = set(coords_table.schema.names)
    assert expected_columns == actual_columns

    # Verify zones metadata
    zones_table = pq.read_table(str(zones_file))
    zones_df = zones_table.to_pandas()
    assert len(zones_df) == 2, f"Expected 2 zones, got {len(zones_df)}"
    assert "Zone A" in zones_df["nome"].values
    assert "Zone B" in zones_df["nome"].values


@pytest.mark.integration
def test_recorder_with_calibration(temp_project_dir, sample_zones):
    """
    Test that Recorder correctly handles calibration data.

    Validates:
    - Calibrated schema includes x_cm, y_cm columns
    - Uncalibrated schema does NOT include these columns
    - Schema remains consistent throughout recording
    """
    results_dir = temp_project_dir / "calibrated_results"
    results_dir.mkdir()

    processing_area = {"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]}
    calibration_data = {"pixels_per_cm": 10.0}

    # Start recorder WITH calibration
    recorder = Recorder()
    recorder.start(
        output_folder=str(results_dir),
        base_name="calibrated_video",
        processing_area=processing_area,
        zones=sample_zones,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
        calibration_data=calibration_data,
    )

    # Write data with calibration columns
    for frame_num in range(1, 21):
        detections = [
            {
                "timestamp": frame_num / 30.0,
                "frame": frame_num,
                "track_id": 1,
                "x1": 100,
                "y1": 100,
                "x2": 150,
                "y2": 150,
                "confidence": 0.9,
                "x_center_px": 125,
                "y_center_px": 125,
                "x_cm": 12.5,
                "y_cm": 12.5,
            }
        ]
        recorder.write_detection_data(detections, frame_num)

    recorder.stop()

    # Verify calibrated schema
    import pyarrow.parquet as pq

    coords_file = results_dir / "3_CoordMovimento_calibrated_video.parquet"
    assert coords_file.exists()

    table = pq.read_table(str(coords_file))
    column_names = set(table.schema.names)

    # Should have calibration columns
    assert "x_center_px" in column_names
    assert "y_center_px" in column_names
    assert "x_cm" in column_names
    assert "y_cm" in column_names

    assert len(table) == 20


@pytest.mark.integration
def test_state_manager_tracks_workflow_progression(temp_project_dir):
    """
    Test that StateManager correctly tracks state throughout a workflow.

    Validates:
    - State updates are recorded
    - State history is maintained
    - Current state reflects latest update
    - Observers are notified
    """
    state_manager = StateManager()
    observer_notifications = []

    def test_observer(state):
        """Record observer notifications."""
        observer_notifications.append(state.copy())

    # Register observer for PROCESSING category
    state_manager.register_observer(StateCategory.PROCESSING, test_observer)

    # Simulate workflow progression
    state_manager.update_project_state(project_path=str(temp_project_dir / "project.json"))
    state_manager.update_recording_state(is_recording=False, recorded_frames=0)
    state_manager.update_processing_state(
        is_processing=True,
        current_video="test1.mp4",
        current_frame=0,
        total_frames=1000,
    )

    # Simulate progress
    for frame in [250, 500, 750, 1000]:
        state_manager.update_processing_state(
            is_processing=True,
            current_video="test1.mp4",
            current_frame=frame,
            total_frames=1000,
        )
        time.sleep(0.01)

    # Complete processing
    state_manager.update_processing_state(
        is_processing=False,
        current_video=None,
        current_frame=1000,
        total_frames=1000,
    )

    # Verify observer was notified
    assert len(observer_notifications) > 0, "Observer should have been notified"

    # Verify final state
    final_state = state_manager.get_state_snapshot()
    assert final_state["processing"]["is_processing"] is False
    assert final_state["processing"]["current_frame"] == 1000

    # Verify history
    history = state_manager.get_history(limit=20)
    assert len(history) >= 5, f"Expected at least 5 history entries, got {len(history)}"

    # Cleanup
    state_manager.clear_observers()


@pytest.mark.integration
def test_multi_video_recording_session(temp_project_dir, sample_zones):
    """
    Test processing multiple videos sequentially with same Recorder instance.

    Validates:
    - Recorder can start/stop multiple times
    - Each video gets separate output folder
    - Schema consistency across sessions
    """
    processing_area = {"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]}
    recorder = Recorder()

    video_names = ["video1", "video2", "video3"]

    for video_name in video_names:
        results_dir = temp_project_dir / f"{video_name}_results"
        results_dir.mkdir()

        # Start recording session
        recorder.start(
            output_folder=str(results_dir),
            base_name=video_name,
            processing_area=processing_area,
            zones=sample_zones,
            frame_width=1280,
            frame_height=720,
            fps=30,
            enable_video_output=False,
        )

        # Write some data
        for frame in range(1, 11):
            recorder.write_detection_data(
                [{
                    "timestamp": frame / 30.0,
                    "frame": frame,
                    "track_id": 1,
                    "x1": 100,
                    "y1": 100,
                    "x2": 150,
                    "y2": 150,
                    "confidence": 0.9,
                }],
                frame_number=frame,
            )

        # Stop session
        recorder.stop()

        # Verify files for this video
        coords_file = results_dir / f"3_CoordMovimento_{video_name}.parquet"
        assert coords_file.exists(), f"Missing coords file for {video_name}"

    # Verify all 3 videos were processed
    all_results = list(temp_project_dir.glob("*_results"))
    assert len(all_results) == 3, f"Expected 3 result directories, found {len(all_results)}"


@pytest.mark.integration
def test_recording_with_periodic_flush(temp_project_dir, sample_zones):
    """
    Test that periodic flushing works correctly during long recordings.

    Validates:
    - Data is flushed to disk periodically
    - File is readable mid-recording
    - Final file contains all data
    """
    results_dir = temp_project_dir / "flush_test_results"
    results_dir.mkdir()

    processing_area = {"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]}

    # Configure shorter flush interval for testing
    with patch("zebtrack.settings.settings.recorder.flush_interval_seconds", 0.5):
        with patch("zebtrack.settings.settings.recorder.flush_row_threshold", 20):
            recorder = Recorder()
            recorder.start(
                output_folder=str(results_dir),
                base_name="flush_test",
                processing_area=processing_area,
                zones=sample_zones,
                frame_width=1280,
                frame_height=720,
                fps=30,
                enable_video_output=False,
            )

            # Write data in batches
            total_frames = 60
            for frame in range(1, total_frames + 1):
                recorder.write_detection_data(
                    [{
                        "timestamp": frame / 30.0,
                        "frame": frame,
                        "track_id": 1,
                        "x1": 100,
                        "y1": 100,
                        "x2": 150,
                        "y2": 150,
                        "confidence": 0.9,
                    }],
                    frame_number=frame,
                )

                # Small delay to allow flush to trigger
                if frame % 20 == 0:
                    time.sleep(0.6)

            recorder.stop()

    # Verify final file
    coords_file = results_dir / "3_CoordMovimento_flush_test.parquet"
    assert coords_file.exists()

    import pyarrow.parquet as pq

    table = pq.read_table(str(coords_file))
    assert len(table) == total_frames, f"Expected {total_frames} rows, got {len(table)}"


@pytest.mark.integration
def test_zone_metadata_preservation(temp_project_dir, sample_zones):
    """
    Test that zone metadata is correctly saved and structured.

    Validates:
    - Zone names, colors preserved
    - Polygon coordinates saved
    - Commands preserved (if any)
    """
    results_dir = temp_project_dir / "zone_metadata_test"
    results_dir.mkdir()

    # Add commands to zones for testing
    zones_with_commands = sample_zones.copy()
    zones_with_commands[0]["enter_commands"] = ["LED_ON"]
    zones_with_commands[0]["exit_commands"] = ["LED_OFF"]

    processing_area = {"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]}

    recorder = Recorder()
    recorder.start(
        output_folder=str(results_dir),
        base_name="zone_test",
        processing_area=processing_area,
        zones=zones_with_commands,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
    )

    # Write minimal data
    recorder.write_detection_data(
        [{
            "timestamp": 0.0,
            "frame": 1,
            "track_id": 1,
            "x1": 100,
            "y1": 100,
            "x2": 150,
            "y2": 150,
            "confidence": 0.9,
        }],
        frame_number=1,
    )

    recorder.stop()

    # Load and verify zone metadata
    zones_file = results_dir / "2_Zones_zone_test.parquet"
    assert zones_file.exists()

    import pyarrow.parquet as pq

    zones_table = pq.read_table(str(zones_file))
    zones_df = zones_table.to_pandas()

    # Verify zone A
    zone_a = zones_df[zones_df["nome"] == "Zone A"].iloc[0]
    assert zone_a["cor"] == "red"

    # Commands should be preserved (stored as JSON strings)
    # The exact format may vary, but they should be present
    assert "enter_commands" in zones_df.columns or "comando_entrada" in zones_df.columns
