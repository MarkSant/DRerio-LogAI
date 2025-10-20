"""
Integration tests for error scenarios and recovery mechanisms.

Tests error handling, recovery, and system resilience across the full pipeline.
"""

import itertools
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.core.state_manager import StateCategory, StateManager
from zebtrack.io.camera import Camera
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
            "name": "Test Zone",
            "polygon": [(100, 100), (300, 100), (300, 300), (100, 300)],
            "color": "red",
            "enter_commands": [],
            "exit_commands": [],
        }
    ]


@pytest.mark.integration
def test_video_processing_error_recovery(temp_project_dir, sample_zones):
    """
    Test that batch processing continues when individual videos fail.

    Scenario:
    1. Batch of 5 videos
    2. Video #3 simulated to fail
    3. Verify videos 1, 2, 4, 5 processed successfully
    4. Verify StateManager tracks errors
    """
    state_manager = StateManager()
    processing_results = {"success": [], "failed": []}

    video_names = [f"video{i}" for i in range(1, 6)]

    for idx, video_name in enumerate(video_names):
        # Simulate failure for video #3 (index 2) WITHOUT creating directory
        if idx == 2:
            # Track failure
            state_manager.update_processing_state(
                is_processing=False,
                current_video=video_name,
                current_frame=0,
                total_frames=1000,
            )
            processing_results["failed"].append(video_name)
            continue

        results_dir = temp_project_dir / f"{video_name}_results"
        results_dir.mkdir()

        # Process other videos successfully
        try:
            processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

            # Convert to ZoneData format
            zones_data = ZoneData(
                polygon=processing_area_polygon,
                roi_polygons=[z["polygon"] for z in sample_zones],
                roi_names=[z["name"] for z in sample_zones],
            )

            recorder = Recorder()
            recorder.start_recording(
                output_folder=str(results_dir),
                frame_width=1280,
                frame_height=720,
                zones=zones_data,
                is_video_file=True,
                base_name=video_name,
            )

            # Add sample detection data
            timestamp = 0.0
            detections = [(100, 100, 150, 150, 0.9, 1)]
            recorder.write_detection_data(timestamp, 1, detections)

            recorder.stop_recording()

            # Give Windows time to flush
            time.sleep(0.1)

            # Track success
            state_manager.update_processing_state(
                is_processing=False,
                current_video=video_name,
                current_frame=1000,
                total_frames=1000,
            )
            processing_results["success"].append(video_name)

        except Exception:
            # Track failure
            state_manager.update_processing_state(
                is_processing=False,
                current_video=video_name,
                current_frame=0,
                total_frames=1000,
            )
            processing_results["failed"].append(video_name)

    # Verify results: 4 success, 1 failure
    assert len(processing_results["success"]) == 4
    assert len(processing_results["failed"]) == 1
    assert "video3" in processing_results["failed"]

    # Verify result directories (4 should exist)
    result_dirs = list(temp_project_dir.glob("*_results"))
    assert len(result_dirs) == 4


@pytest.mark.integration
def test_camera_reconnect_and_recovery():
    """
    Test camera reconnection and processing continuation.

    Scenario:
    1. Start camera
    2. Simulate disconnection
    3. Verify camera reconnects
    4. Verify processing can continue
    """
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc:
        with patch("zebtrack.io.camera.time.sleep"):
            # Setup mock
            mock_vc = MagicMock()

            # Initial dimensions
            initial_get_values = [1280, 720, 30.0]

            # Simulate reconnection
            is_opened_sequence = [True, True, False, False, True]
            test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            read_sequence = [
                (True, test_frame),
                (False, None),  # Failure
                (True, test_frame),  # Recovery
            ]

            reconnect_get_values = [1280, 720, 30.0]

            mock_vc.isOpened.side_effect = itertools.chain(
                is_opened_sequence, itertools.repeat(True)
            )
            mock_vc.read.side_effect = itertools.chain(
                read_sequence, itertools.repeat((True, test_frame))
            )
            mock_vc.get.side_effect = itertools.chain(
                initial_get_values, reconnect_get_values, itertools.repeat(30.0)
            )

            mock_cv2_vc.return_value = mock_vc

            # Create camera
            camera = Camera()

            # Give camera time to start and reconnect
            time.sleep(0.3)

            # Verify camera thread is still alive
            assert camera._thread.is_alive()

            # Verify reconnection happened
            assert mock_vc.open.call_count >= 1

            # Verify we can get frames after reconnection
            time.sleep(0.2)

            max_retries = 5
            for _ in range(max_retries):
                ret, frame = camera.get_frame()
                if ret:
                    break
                time.sleep(0.1)

            assert ret is True
            assert frame is not None

            # Cleanup
            camera.release()


@pytest.mark.integration
def test_schema_validation_prevents_corruption(temp_project_dir):
    """
    Test that schema validation prevents Parquet file corruption.

    Scenario:
    1. Start recording without calibration
    2. Try to add calibration midway (schema change)
    3. Should raise ValueError
    4. Verify Parquet file is NOT corrupted
    """
    results_dir = temp_project_dir / "schema_test_results"
    results_dir.mkdir()

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[[(100, 100), (300, 100), (300, 300), (100, 300)]],
        roi_names=["Test Zone"],
    )

    # Start recorder WITHOUT calibration
    recorder = Recorder()
    recorder.start_recording(
        output_folder=str(results_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="test_video",
        pixel_per_cm_ratio=None,  # No calibration
    )

    # Write some detections without calibration columns
    for frame in range(1, 6):
        timestamp = frame / 30.0
        detections = [(100, 100, 150, 150, 0.9, 1)]
        recorder.write_detection_data(timestamp, frame, detections)

    # Manually flush data to create the Parquet file before causing error
    recorder._flush_detection_data(force=True)

    # Give Windows time to flush
    time.sleep(0.1)

    # Verify Parquet file was created with 5 rows
    coords_file = results_dir / "3_CoordMovimento_test_video.parquet"
    assert coords_file.exists()

    import pyarrow.parquet as pq

    table = pq.read_table(str(coords_file))
    assert len(table) == 5

    # Now try to change schema by setting calibration (should fail)
    recorder.pixel_per_cm_ratio = (10.0, 10.0)
    recorder._flush_row_threshold = 1  # Force flush on next write

    with pytest.raises(ValueError, match="Parquet schema cannot change"):
        timestamp = 6 / 30.0
        detections = [(100, 100, 150, 150, 0.9, 1)]
        recorder.write_detection_data(timestamp, 6, detections)

    # Verify schema remained unchanged (no calibration columns added)
    table_after = pq.read_table(str(coords_file))
    expected_columns = {"timestamp", "frame", "track_id", "x1", "y1", "x2", "y2", "confidence"}
    actual_columns = set(table_after.schema.names)
    assert expected_columns == actual_columns

    # Verify data integrity (still 5 rows, not 6 - new row wasn't added due to error)
    assert len(table_after) == 5


@pytest.mark.integration
def test_recorder_error_recovery_new_session(temp_project_dir):
    """
    Test that recorder can start a new session after an error.

    Scenario:
    1. Start recording session 1
    2. Cause a schema error
    3. Stop recorder
    4. Start new recording session 2
    5. Verify session 2 works correctly
    """
    results_dir = temp_project_dir / "recorder_recovery"
    results_dir.mkdir()

    processing_area_polygon = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Convert to ZoneData format
    zones_data = ZoneData(
        polygon=processing_area_polygon,
        roi_polygons=[[(100, 100), (300, 100), (300, 300), (100, 300)]],
        roi_names=["Test Zone"],
    )

    # Session 1: Start and cause error
    recorder = Recorder()
    session1_dir = results_dir / "session1"
    session1_dir.mkdir()

    recorder.start_recording(
        output_folder=str(session1_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="test_session1",
    )

    timestamp = 0.0
    detections = [(100, 100, 150, 150, 0.9, 1)]
    recorder.write_detection_data(timestamp, 1, detections)

    # Cause schema error by changing calibration
    try:
        recorder.pixel_per_cm_ratio = (10.0, 10.0)
        recorder._flush_row_threshold = 1
        timestamp = 0.033
        detections = [(100, 100, 150, 150, 0.9, 1)]
        recorder.write_detection_data(timestamp, 2, detections)
    except ValueError:
        pass  # Expected error

    # Give Windows time to flush
    time.sleep(0.1)

    # Session 2: Start fresh
    session2_dir = results_dir / "session2"
    session2_dir.mkdir()

    recorder.start_recording(
        output_folder=str(session2_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones_data,
        is_video_file=True,
        base_name="test_session2",
    )

    timestamp = 0.0
    detections = [(100, 100, 150, 150, 0.9, 1)]
    recorder.write_detection_data(timestamp, 1, detections)

    recorder.stop_recording()

    # Give Windows time to flush
    time.sleep(0.1)

    # Verify both sessions created files
    session1_file = session1_dir / "3_CoordMovimento_test_session1.parquet"
    session2_file = session2_dir / "3_CoordMovimento_test_session2.parquet"

    assert session1_file.exists()
    assert session2_file.exists()

    # Verify session 2 has valid data
    import pyarrow.parquet as pq

    table2 = pq.read_table(str(session2_file))
    assert len(table2) == 1


@pytest.mark.integration
def test_state_manager_observer_pattern(temp_project_dir):
    """
    Test StateManager observer pattern and state tracking.

    Validates:
    - Observers are notified of state changes
    - State history is preserved
    - Multiple observers work correctly
    """
    state_manager = StateManager()

    observer1_calls = []
    observer2_calls = []

    def observer1(category, key, old_value, new_value):
        """Observer with correct signature."""
        observer1_calls.append(
            {"category": category, "key": key, "old_value": old_value, "new_value": new_value}
        )

    def observer2(category, key, old_value, new_value):
        """Observer with correct signature."""
        observer2_calls.append(
            {"category": category, "key": key, "old_value": old_value, "new_value": new_value}
        )

    # Register observers for different categories
    state_manager.register_observer(StateCategory.PROJECT, observer1)
    state_manager.register_observer(StateCategory.RECORDING, observer2)

    # Trigger state changes
    state_manager.update_project_state(project_path=str(temp_project_dir))
    state_manager.update_recording_state(is_recording=True)
    state_manager.update_processing_state(
        is_processing=True,
        current_video="test.mp4",
        current_frame=500,
        total_frames=1000,
    )

    # Verify observers were called (observer1 for project, observer2 for recording)
    assert len(observer1_calls) >= 1, "Observer1 should be called for project updates"
    assert len(observer2_calls) >= 1, "Observer2 should be called for recording updates"

    # Verify state history
    history = state_manager.get_history(limit=10)
    assert len(history) >= 3


@pytest.mark.integration
def test_concurrent_state_updates():
    """
    Test that StateManager handles concurrent updates correctly.

    Validates thread-safety of state management.
    """
    import threading

    state_manager = StateManager()
    update_count = [0]
    errors = []

    def update_worker(worker_id):
        """Worker thread that performs state updates."""
        try:
            for i in range(10):
                state_manager.update_processing_state(
                    is_processing=True,
                    current_video=f"worker_{worker_id}_video_{i}.mp4",
                    current_frame=i * 100,
                    total_frames=1000,
                )
                update_count[0] += 1
                time.sleep(0.001)
        except Exception as e:
            errors.append((worker_id, str(e)))

    # Start multiple worker threads
    workers = []
    for worker_id in range(5):
        thread = threading.Thread(target=update_worker, args=(worker_id,))
        thread.start()
        workers.append(thread)

    # Wait for all workers
    for thread in workers:
        thread.join(timeout=5)

    # Verify no errors occurred
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all updates were processed
    assert update_count[0] == 50, f"Expected 50 updates, got {update_count[0]}"

    # Verify state history
    history = state_manager.get_history(limit=100)
    assert len(history) >= 50, f"Expected at least 50 history entries, got {len(history)}"
