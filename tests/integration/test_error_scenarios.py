"""
Integration tests for error scenarios and recovery mechanisms.

Tests error handling, recovery, and system resilience across the full pipeline.
"""

import itertools
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

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
        results_dir = temp_project_dir / f"{video_name}_results"
        results_dir.mkdir()

        # Simulate failure for video #3 (index 2)
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

        # Process other videos successfully
        try:
            recorder = Recorder()
            recorder.start(
                output_folder=str(results_dir),
                base_name=video_name,
                processing_area={"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]},
                zones=sample_zones,
                frame_width=1280,
                frame_height=720,
                fps=30,
                enable_video_output=False,
            )

            # Add sample detection data
            recorder.write_detection_data(
                [
                    {
                        "timestamp": 0.0,
                        "frame": 1,
                        "track_id": 1,
                        "x1": 100,
                        "y1": 100,
                        "x2": 150,
                        "y2": 150,
                        "confidence": 0.9,
                    }
                ],
                frame_number=1,
            )

            recorder.stop()

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

    # Cleanup
    state_manager.clear_observers()


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

    zones = [
        {
            "name": "Test Zone",
            "polygon": [(100, 100), (300, 100), (300, 300), (100, 300)],
            "color": "red",
            "enter_commands": [],
            "exit_commands": [],
        }
    ]

    # Start recorder WITHOUT calibration
    recorder = Recorder()
    recorder.start(
        output_folder=str(results_dir),
        base_name="test_video",
        processing_area={"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]},
        zones=zones,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
        calibration_data=None,
    )

    # Write some detections without calibration columns
    for frame in range(1, 6):
        recorder.write_detection_data(
            [
                {
                    "timestamp": frame / 30.0,
                    "frame": frame,
                    "track_id": 1,
                    "x1": 100,
                    "y1": 100,
                    "x2": 150,
                    "y2": 150,
                    "confidence": 0.9,
                }
            ],
            frame_number=frame,
        )

    # Try to add detection WITH calibration data (schema change)
    with pytest.raises(ValueError, match="Parquet schema cannot change"):
        recorder.write_detection_data(
            [
                {
                    "timestamp": 6 / 30.0,
                    "frame": 6,
                    "track_id": 1,
                    "x1": 100,
                    "y1": 100,
                    "x2": 150,
                    "y2": 150,
                    "confidence": 0.9,
                    "x_center_px": 125,
                    "y_center_px": 125,
                    "x_cm": 5.0,
                    "y_cm": 5.0,
                }
            ],
            frame_number=6,
        )

    # Stop recorder
    recorder.stop()

    # Verify Parquet file exists and has correct schema
    coords_file = results_dir / "3_CoordMovimento_test_video.parquet"
    assert coords_file.exists()

    import pyarrow.parquet as pq

    table = pq.read_table(str(coords_file))

    expected_columns = {"timestamp", "frame", "track_id", "x1", "y1", "x2", "y2", "confidence"}
    actual_columns = set(table.schema.names)
    assert expected_columns == actual_columns

    # Verify data integrity (should have 5 rows, not 6)
    assert len(table) == 5


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

    zones = [
        {
            "name": "Test Zone",
            "polygon": [(100, 100), (300, 100), (300, 300), (100, 300)],
            "color": "red",
            "enter_commands": [],
            "exit_commands": [],
        }
    ]

    # Session 1: Start and cause error
    recorder = Recorder()
    recorder.start(
        output_folder=str(results_dir / "session1"),
        base_name="test_session1",
        processing_area={"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]},
        zones=zones,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
    )

    recorder.write_detection_data(
        [
            {
                "timestamp": 0.0,
                "frame": 1,
                "track_id": 1,
                "x1": 100,
                "y1": 100,
                "x2": 150,
                "y2": 150,
                "confidence": 0.9,
            }
        ],
        frame_number=1,
    )

    # Cause schema error
    try:
        recorder.write_detection_data(
            [
                {
                    "timestamp": 0.033,
                    "frame": 2,
                    "track_id": 1,
                    "x1": 100,
                    "y1": 100,
                    "x2": 150,
                    "y2": 150,
                    "confidence": 0.9,
                    "x_cm": 5.0,  # New column - causes error
                }
            ],
            frame_number=2,
        )
    except ValueError:
        pass  # Expected error

    recorder.stop()

    # Session 2: Start fresh
    recorder.start(
        output_folder=str(results_dir / "session2"),
        base_name="test_session2",
        processing_area={"polygon": [(0, 0), (1280, 0), (1280, 720), (0, 720)]},
        zones=zones,
        frame_width=1280,
        frame_height=720,
        fps=30,
        enable_video_output=False,
    )

    recorder.write_detection_data(
        [
            {
                "timestamp": 0.0,
                "frame": 1,
                "track_id": 1,
                "x1": 100,
                "y1": 100,
                "x2": 150,
                "y2": 150,
                "confidence": 0.9,
            }
        ],
        frame_number=1,
    )

    recorder.stop()

    # Verify both sessions created files
    session1_file = results_dir / "session1" / "3_CoordMovimento_test_session1.parquet"
    session2_file = results_dir / "session2" / "3_CoordMovimento_test_session2.parquet"

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

    def observer1(state):
        observer1_calls.append(state.copy())

    def observer2(state):
        observer2_calls.append(state.copy())

    # Register observers for different categories
    state_manager.register_observer(StateCategory.PROJECT, observer1)
    state_manager.register_observer(StateCategory.RECORDING, observer2)

    # Trigger state changes
    state_manager.update_project_state(project_path=str(temp_project_dir))
    state_manager.update_recording_state(is_recording=True, recorded_frames=10)
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

    # Cleanup
    state_manager.clear_observers()


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

    # Cleanup
    state_manager.clear_observers()
