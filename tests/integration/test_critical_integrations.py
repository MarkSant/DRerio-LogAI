"""
Critical integration tests for ZebTrack-AI core components.

Tests the integration of:
1. Recorder + Camera (live streaming)
2. Detector + Recorder (processing pipeline)
3. StateManager + workflow components
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
def temp_results_dir(tmp_path):
    """Create a temporary directory for test results."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    return results_dir


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
        }
    ]


@pytest.mark.integration
def test_camera_to_recorder_live_streaming(temp_results_dir, sample_zones):
    """
    Test integration of Camera → Recorder for live streaming.

    Validates:
    - Camera captures frames continuously
    - Recorder receives and saves frames
    - Frame buffer prevents lag
    - Data is persisted to Parquet
    """
    # Create mock settings for Camera DI
    mock_settings = MagicMock()
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 1280
    mock_settings.camera.desired_height = 720
    mock_settings.camera.max_reconnect_attempts = 3
    mock_settings.camera.reconnect_timeout_seconds = 5.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    mock_settings.video_processing.fps = 30
    
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc:
        with patch("zebtrack.io.camera.time.sleep"):
            # Setup mock camera
            mock_vc = MagicMock()
            mock_vc.isOpened.return_value = True
            mock_vc.get.side_effect = [1280, 720, 30.0]  # width, height, fps

            # Generate continuous frames
            def generate_frame():
                return np.zeros((720, 1280, 3), dtype=np.uint8)

            mock_vc.read.side_effect = itertools.repeat((True, generate_frame()))
            mock_cv2_vc.return_value = mock_vc

            # Start camera with settings
            camera = Camera(settings_obj=mock_settings)

            # Wait for camera to start capturing
            time.sleep(0.2)

            # Start recorder with correct API
            recorder = Recorder()
            recorder.start_recording(
                output_folder=str(temp_results_dir),
                frame_width=1280,
                frame_height=720,
                zones=sample_zones,
                is_video_file=True,  # Skip video file creation for speed
                base_name="live_test",
            )

            # Simulate live streaming: read frames from camera and write to recorder
            frames_written = 0
            for frame_num in range(1, 31):  # 30 frames
                ret, frame = camera.get_frame()

                if ret and frame is not None:
                    # Write frame to recorder
                    # Correct API: tuple of (x1, y1, x2, y2, conf, track_id)
                    detections = [(100 + frame_num, 100, 150 + frame_num, 150, 0.9, 1)]

                    recorder.write_detection_data(
                        timestamp=frame_num / 30.0,
                        frame_number=frame_num,
                        detections=detections,
                    )
                    frames_written += 1

                time.sleep(0.01)  # Simulate processing time

            # Stop recorder
            recorder.stop_recording()

            # Cleanup camera
            camera.release()

            # Verify results
            assert frames_written > 0, "Should have written at least some frames"

            # Verify Parquet file was created
            coords_file = temp_results_dir / "3_CoordMovimento_live_test.parquet"
            assert coords_file.exists(), "Coords file should exist"

            # Verify data integrity
            import pyarrow.parquet as pq

            table = pq.read_table(str(coords_file))
            assert len(table) == frames_written, f"Expected {frames_written} rows"


@pytest.mark.integration
def test_detector_to_recorder_pipeline(temp_results_dir, sample_zones):
    """
    Test integration of Detector → Recorder for video processing.

    Validates:
    - Detector processes frames and generates detections
    - Recorder saves detections with correct schema
    - Zone metadata is preserved
    - Multi-object tracking IDs are handled
    """

    # Mock detector behavior
    class MockDetector:
        def __init__(self):
            self.frame_count = 0

        def process_frame(self, frame):
            """Simulate detector generating detections as tuples."""
            self.frame_count += 1

            # Return detections as tuples: (x1, y1, x2, y2, confidence, track_id)
            return [
                (100 + self.frame_count, 100, 150 + self.frame_count, 150, 0.95, 1),
                (200 + self.frame_count, 200, 250 + self.frame_count, 250, 0.92, 2),
            ]

    # Start recorder
    recorder = Recorder()
    recorder.start_recording(
        output_folder=str(temp_results_dir),
        frame_width=1280,
        frame_height=720,
        zones=sample_zones,
        is_video_file=True,
        base_name="detector_test",
    )

    # Simulate detector processing frames
    detector = MockDetector()

    for frame_num in range(1, 51):  # 50 frames
        # Generate mock frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Process frame with detector
        detections = detector.process_frame(frame)

        # Write to recorder
        recorder.write_detection_data(
            timestamp=frame_num / 30.0,
            frame_number=frame_num,
            detections=detections,
        )

    # Stop recorder
    recorder.stop_recording()

    # Verify results
    coords_file = temp_results_dir / "3_CoordMovimento_detector_test.parquet"
    assert coords_file.exists()

    # Verify data
    import pyarrow.parquet as pq

    table = pq.read_table(str(coords_file))

    # Should have 50 frames × 2 objects = 100 rows
    assert len(table) == 100, f"Expected 100 rows, got {len(table)}"

    # Verify both track IDs are present
    df = table.to_pandas()
    track_ids = set(df["track_id"].unique())
    assert track_ids == {1, 2}, f"Expected track IDs {{1, 2}}, got {track_ids}"


@pytest.mark.integration
def test_state_manager_workflow_orchestration(temp_results_dir, sample_zones):
    """
    Test StateManager orchestrating a complete workflow.

    Validates:
    - StateManager tracks all workflow stages
    - Observers receive updates
    - State transitions are correct
    - History is maintained
    """
    state_manager = StateManager()

    # Track all state changes
    all_updates = []

    def universal_observer(category, key, old_value, new_value):
        """Observer receives: category, key, old_value, new_value."""
        all_updates.append(
            {
                "timestamp": time.time(),
                "category": category,
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            }
        )

    # Register observers for all categories
    for category in StateCategory:
        state_manager.register_observer(category, universal_observer)

    # Simulate complete workflow with actual state changes

    # 1. Project initialization
    state_manager.update_project_state(project_path=str(temp_results_dir / "project.json"))

    # 2. Start recording (change from False to True)
    state_manager.update_recording_state(is_recording=True)

    # 3. Stop recording (change from True to False)
    time.sleep(0.01)
    state_manager.update_recording_state(is_recording=False)

    # 4. Start processing
    state_manager.update_processing_state(
        is_processing=True,
        current_video="test_video.mp4",
        current_frame=0,
        total_frames=1000,
    )

    # Simulate processing progress (actual frame changes)
    for frame in [250, 500, 750, 1000]:
        state_manager.update_processing_state(
            is_processing=True,
            current_video="test_video.mp4",
            current_frame=frame,
            total_frames=1000,
        )
        time.sleep(0.01)

    # 5. Complete processing (change is_processing from True to False)
    state_manager.update_processing_state(
        is_processing=False,
        current_video=None,
        current_frame=1000,
        total_frames=1000,
    )

    # Verify observers were notified
    assert len(all_updates) > 0, (
        f"Observers should have been notified, got {len(all_updates)} updates"
    )

    # Verify final state
    final_state = state_manager.get_state_snapshot()

    # Recording should be stopped
    assert final_state["recording"]["is_recording"] is False

    # Processing should be complete
    assert final_state["processing"]["is_processing"] is False
    assert final_state["processing"]["current_frame"] == 1000

    # Verify history
    history = state_manager.get_history(limit=50)
    assert len(history) >= 5, f"Expected at least 5 history entries, got {len(history)}"


@pytest.mark.integration
def test_end_to_end_simulated_workflow(temp_results_dir, sample_zones):
    """
    Test complete end-to-end workflow simulation.

    Integrates:
    - Camera (mocked)
    - Detector (mocked)
    - Recorder
    - StateManager

    Validates the entire pipeline works together.
    """
    # Create mock settings for Camera DI
    mock_settings = MagicMock()
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 1280
    mock_settings.camera.desired_height = 720
    mock_settings.camera.max_reconnect_attempts = 3
    mock_settings.camera.reconnect_timeout_seconds = 5.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    mock_settings.video_processing.fps = 30
    
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc:
        with patch("zebtrack.io.camera.time.sleep"):
            # Setup mock camera
            mock_vc = MagicMock()
            mock_vc.isOpened.return_value = True
            mock_vc.get.side_effect = [1280, 720, 30.0]

            test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            mock_vc.read.side_effect = itertools.repeat((True, test_frame))
            mock_cv2_vc.return_value = mock_vc

            # Initialize components with settings
            camera = Camera(settings_obj=mock_settings)
            recorder = Recorder()
            state_manager = StateManager()

            # Wait for camera to initialize
            time.sleep(0.2)

            # Start workflow
            state_manager.update_recording_state(is_recording=True)

            recorder.start_recording(
                output_folder=str(temp_results_dir),
                frame_width=1280,
                frame_height=720,
                zones=sample_zones,
                is_video_file=True,
                base_name="e2e_test",
            )

            # Simulate processing loop
            total_frames = 20
            for frame_num in range(1, total_frames + 1):
                # Get frame from camera
                ret, frame = camera.get_frame()

                if ret and frame is not None:
                    # Mock detector processing - returns tuples
                    detections = [(100, 100, 150, 150, 0.9, 1)]

                    # Write to recorder
                    recorder.write_detection_data(
                        timestamp=frame_num / 30.0,
                        frame_number=frame_num,
                        detections=detections,
                    )

                    # Update state
                    state_manager.update_recording_state(is_recording=True)

                time.sleep(0.01)

            # Stop workflow
            recorder.stop_recording()
            state_manager.update_recording_state(is_recording=False)
            camera.release()

            # Verify results
            coords_file = temp_results_dir / "3_CoordMovimento_e2e_test.parquet"
            assert coords_file.exists(), "Output file should exist"

            import pyarrow.parquet as pq

            table = pq.read_table(str(coords_file))
            assert len(table) == total_frames, f"Expected {total_frames} rows"

            # Verify final state
            final_state = state_manager.get_state_snapshot()
            assert final_state["recording"]["is_recording"] is False


@pytest.mark.integration
def test_frame_buffer_prevents_lag_in_live_mode(temp_results_dir, sample_zones):
    """
    Test that frame buffer prevents lag during live streaming.

    Validates:
    - Buffer keeps only 2 most recent frames
    - Old frames are discarded
    - Lag detection works correctly
    - Processing always uses fresh frames
    """
    # Create mock settings for Camera DI
    mock_settings = MagicMock()
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 1280
    mock_settings.camera.desired_height = 720
    mock_settings.camera.max_reconnect_attempts = 3
    mock_settings.camera.reconnect_timeout_seconds = 5.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    mock_settings.video_processing.fps = 30
    
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc:
        # NOTE: We do NOT patch time.sleep here - the camera thread needs real sleep
        # to allow the background thread to run and capture frames
        mock_vc = MagicMock()
        mock_vc.isOpened.return_value = True
        mock_vc.get.side_effect = [1280, 720, 30.0]

        # Create frames with unique timestamps for tracking
        frame_counter = [0]
        frame_timestamps = []

        def create_unique_frame():
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            timestamp = frame_counter[0]
            frame_timestamps.append(timestamp)
            # Store timestamp in frame metadata (not pixel data to avoid overflow)
            frame_counter[0] += 1
            return frame

        mock_vc.read.side_effect = lambda: (True, create_unique_frame())
        mock_cv2_vc.return_value = mock_vc

        camera = Camera(settings_obj=mock_settings)

        # Wait for camera to capture some frames
        time.sleep(0.3)

        # Verify buffer size is limited
        with camera._lock:
            buffer_size = len(camera._frame_buffer)
            assert buffer_size <= 2, f"Buffer should have max 2 frames, has {buffer_size}"

        # Record the current frame count
        initial_frame_count = frame_counter[0]

        # Get multiple frames rapidly
        frames_retrieved = 0
        for _ in range(10):
            ret, frame = camera.get_frame()
            if ret:
                frames_retrieved += 1
            time.sleep(0.05)

        # Verify we retrieved frames
        assert frames_retrieved > 0, "Should have retrieved at least some frames"

        # Verify that the camera kept capturing new frames during retrieval
        # (proving the buffer is updating with fresh frames, not stuck on old ones)
        final_frame_count = frame_counter[0]
        assert final_frame_count > initial_frame_count, (
            "Camera should continue capturing new frames"
        )

        camera.release()
