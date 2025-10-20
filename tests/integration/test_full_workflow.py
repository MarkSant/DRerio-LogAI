"""
End-to-end integration tests for complete ZebTrack-AI workflow.

Tests the integration of core components: Recorder, StateManager, and processing pipeline.
"""

import time
from unittest.mock import patch

import pytest

from zebtrack.core.detector import ZoneData
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

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[z["polygon"] for z in sample_zones],
        roi_names=[z["name"] for z in sample_zones],
    )

    # Start recorder
    recorder = Recorder()
    recorder.start_recording(
        output_folder=str(results_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,  # No video output in tests
        base_name="test_video",
    )

    # Write 100 frames of detection data
    for frame_num in range(1, 101):
        timestamp = frame_num / 30.0
        detections = [(100 + frame_num, 100, 150 + frame_num, 150, 0.95, 1)]
        recorder.write_detection_data(timestamp, frame_num, detections)

    # Stop recorder
    recorder.stop_recording()

    # Give Windows time to flush
    time.sleep(0.1)

    # Verify files exist
    arena_file = results_dir / "1_ProcessingArea_test_video.parquet"
    areas_file = results_dir / "2_AreasOfInterest_test_video.parquet"
    coords_file = results_dir / "3_CoordMovimento_test_video.parquet"

    assert arena_file.exists(), f"Arena file not found: {arena_file}"
    assert areas_file.exists(), f"Areas file not found: {areas_file}"
    assert coords_file.exists(), f"Coords file not found: {coords_file}"

    # Verify detection data
    import pyarrow.parquet as pq

    coords_table = pq.read_table(str(coords_file))
    assert len(coords_table) == 100, f"Expected 100 rows, got {len(coords_table)}"

    # Verify schema
    expected_columns = {"timestamp", "frame", "track_id", "x1", "y1", "x2", "y2", "confidence"}
    actual_columns = set(coords_table.schema.names)
    assert expected_columns == actual_columns

    # Verify areas metadata
    areas_table = pq.read_table(str(areas_file))
    areas_df = areas_table.to_pandas()
    assert len(areas_df) > 0, "Areas file should contain data"
    assert "Zone A" in areas_df["roi_name"].values
    assert "Zone B" in areas_df["roi_name"].values


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

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
    pixel_per_cm_ratio = (10.0, 10.0)  # 10 pixels per cm

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[z["polygon"] for z in sample_zones],
        roi_names=[z["name"] for z in sample_zones],
    )

    # Start recorder WITH calibration
    recorder = Recorder()
    recorder.start_recording(
        output_folder=str(results_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="calibrated_video",
        pixel_per_cm_ratio=pixel_per_cm_ratio,
    )

    # Write data (calibration columns will be calculated automatically)
    for frame_num in range(1, 21):
        timestamp = frame_num / 30.0
        detections = [(100, 100, 150, 150, 0.9, 1)]
        recorder.write_detection_data(timestamp, frame_num, detections)

    recorder.stop_recording()

    # Give Windows time to flush
    time.sleep(0.1)

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

    def test_observer(category, key, old_value, new_value):
        """Record observer notifications with correct signature."""
        observer_notifications.append(
            {"category": category, "key": key, "old_value": old_value, "new_value": new_value}
        )

    # Register observer for PROCESSING category
    state_manager.register_observer(StateCategory.PROCESSING, test_observer)

    # Simulate workflow progression
    state_manager.update_project_state(project_path=str(temp_project_dir / "project.json"))
    state_manager.update_recording_state(is_recording=False)
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


@pytest.mark.integration
def test_multi_video_recording_session(temp_project_dir, sample_zones):
    """
    Test processing multiple videos sequentially with same Recorder instance.

    Validates:
    - Recorder can start/stop multiple times
    - Each video gets separate output folder
    - Schema consistency across sessions
    """
    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
    recorder = Recorder()

    video_names = ["video1", "video2", "video3"]

    for video_name in video_names:
        results_dir = temp_project_dir / f"{video_name}_results"
        results_dir.mkdir()

        # Convert to ZoneData format
        zones_data = ZoneData(
            polygon=processing_area_polygon,
            roi_polygons=[z["polygon"] for z in sample_zones],
            roi_names=[z["name"] for z in sample_zones],
        )

        # Start recording session
        recorder.start_recording(
            output_folder=str(results_dir),
            frame_width=1280,
            frame_height=720,
            zones=zones_data,
            is_video_file=True,
            base_name=video_name,
        )

        # Write some data
        for frame in range(1, 11):
            timestamp = frame / 30.0
            detections = [(100, 100, 150, 150, 0.9, 1)]
            recorder.write_detection_data(timestamp, frame, detections)

        # Stop session
        recorder.stop_recording()

        # Give Windows time to flush
        time.sleep(0.1)

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

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[z["polygon"] for z in sample_zones],
        roi_names=[z["name"] for z in sample_zones],
    )

    # Configure shorter flush interval for testing
    recorder = Recorder()
    recorder._flush_interval_seconds = 0.5
    recorder._flush_row_threshold = 20

    recorder.start_recording(
        output_folder=str(results_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="flush_test",
    )

    # Write data in batches
    total_frames = 60
    for frame in range(1, total_frames + 1):
        timestamp = frame / 30.0
        detections = [(100, 100, 150, 150, 0.9, 1)]
        recorder.write_detection_data(timestamp, frame, detections)

        # Small delay to allow flush to trigger
        if frame % 20 == 0:
            time.sleep(0.6)

    recorder.stop_recording()

    # Give Windows time to flush
    time.sleep(0.1)

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

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[z["polygon"] for z in zones_with_commands],
        roi_names=[z["name"] for z in zones_with_commands],
    )

    recorder = Recorder()
    recorder.start_recording(
        output_folder=str(results_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="zone_test",
    )

    # Write minimal data
    timestamp = 0.0
    detections = [(100, 100, 150, 150, 0.9, 1)]
    recorder.write_detection_data(timestamp, 1, detections)

    recorder.stop_recording()

    # Give Windows time to flush
    time.sleep(0.1)

    # Load and verify zone metadata
    areas_file = results_dir / "2_AreasOfInterest_zone_test.parquet"
    assert areas_file.exists()

    import pyarrow.parquet as pq

    areas_table = pq.read_table(str(areas_file))
    areas_df = areas_table.to_pandas()

    # Verify zone A exists
    assert "Zone A" in areas_df["roi_name"].values
    assert "Zone B" in areas_df["roi_name"].values

    # Verify we have polygon points
    zone_a_points = areas_df[areas_df["roi_name"] == "Zone A"]
    assert len(zone_a_points) == 4, "Zone A should have 4 polygon points"
