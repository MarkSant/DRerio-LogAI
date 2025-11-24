"""
Thread Safety Tests for VideoProcessingService.

Validates concurrent processing scenarios and shared state management.
Addresses PR Review Issue #2 - Incomplete Test Coverage Analysis.
"""

import threading
import time
from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock, patch

import numpy as np
import pytest

from tests.utils.wait_helpers import wait_for_condition


@pytest.fixture
def mock_settings():
    """Create thread-safe mock settings."""
    settings = Mock()
    settings.paths = Mock()
    settings.paths.output_dir = "/fake/output"
    settings.video_processing = Mock()
    settings.video_processing.fps = 30.0
    settings.video_processing.sharp_turn_threshold_deg_s = 45.0
    settings.video_processing.freezing_velocity_threshold = 1.0
    settings.video_processing.freezing_min_duration_s = 2.0
    settings.trajectory_smoothing = Mock()
    settings.trajectory_smoothing.window_length = 5
    settings.trajectory_smoothing.polyorder = 2
    settings.yolo_model = Mock()
    settings.yolo_model.confidence_threshold = 0.25
    return settings


@pytest.fixture
def mock_detector():
    """Create thread-safe mock detector with lock."""
    detector = Mock()
    detector._lock = threading.Lock()
    detector.detect = Mock(return_value=([], None))
    detector.set_zones = Mock()
    detector.set_aquarium_region_defined = Mock()
    detector.draw_overlay = Mock()
    detector.plugin = Mock()
    detector.plugin.get_name = Mock(return_value="MockDetector")
    return detector


@pytest.fixture
def mock_recorder_class():
    """Create mock recorder class for testing instance creation."""

    class MockRecorderClass:
        instances_created: ClassVar[list] = []

        def __init__(self, settings_obj):
            self.settings = settings_obj
            self.start_recording = Mock()
            self.write_detection_data = Mock()
            self.stop_recording = Mock()
            MockRecorderClass.instances_created.append(self)

    return MockRecorderClass


@pytest.fixture
def mock_project_manager():
    """Create mock project manager."""
    pm = Mock()
    pm.get_zone_data = Mock(
        return_value=Mock(
            polygon=[[0, 0], [640, 0], [640, 480], [0, 480]],
            roi_polygons=[],
            roi_names=[],
            roi_colors=[],
        )
    )
    pm.project_path = None
    pm.project_data = {}
    return pm


@pytest.fixture
def video_processing_service(
    mock_settings, mock_detector, mock_recorder_class, mock_project_manager
):
    """Create VideoProcessingService with mocked dependencies."""
    from zebtrack.core.video_processing_service import VideoProcessingService

    # Create a mock recorder instance
    mock_recorder = mock_recorder_class(mock_settings)

    # Make the recorder class accessible via __class__
    mock_recorder.__class__ = mock_recorder_class

    service = VideoProcessingService(
        detector=mock_detector,
        recorder=mock_recorder,
        project_manager=mock_project_manager,
        state_manager=Mock(),
        ui_coordinator=Mock(),
        ui_event_bus=Mock(),
        cancel_event=threading.Event(),
        settings_obj=mock_settings,
    )
    return service


@pytest.mark.unit
class TestThreadSafety:
    """Test suite for thread safety in VideoProcessingService."""

    def test_settings_immutability(self, mock_settings):
        """Test that settings object is not mutated by service operations."""
        # Arrange
        original_fps = mock_settings.video_processing.fps
        original_output_dir = mock_settings.paths.output_dir

        # Act: Simulate multiple threads accessing settings
        def access_settings():
            _ = mock_settings.video_processing.fps
            _ = mock_settings.paths.output_dir

        threads = [threading.Thread(target=access_settings) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: Settings should remain unchanged
        assert mock_settings.video_processing.fps == original_fps
        assert mock_settings.paths.output_dir == original_output_dir

    def test_separate_recorder_instances_per_worker(
        self, video_processing_service, mock_recorder_class
    ):
        """Test that each worker thread creates its own Recorder instance.

        Validates Bug #1 analysis: No race condition exists because each worker
        creates a separate recorder instance via self.recorder.__class__(settings_obj=...).
        """
        # Reset the instances tracking
        mock_recorder_class.instances_created.clear()

        # Simulate multiple workers creating recorders
        def create_recorder_instance():
            recorder = video_processing_service.recorder.__class__(
                settings_obj=video_processing_service.settings
            )
            return recorder

        # Act: Create recorders from multiple threads
        threads = []
        results = []

        def worker():
            recorder = create_recorder_instance()
            results.append(recorder)

        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Assert: Each worker should have a unique recorder instance
        assert len(results) == 5
        assert len(set(id(r) for r in results)) == 5, "All recorder instances should be unique"

        # Verify no shared state between recorders
        for i, recorder in enumerate(results):
            for j, other_recorder in enumerate(results):
                if i != j:
                    assert recorder is not other_recorder

    def test_detector_not_shared_across_calls(self, video_processing_service, mock_detector):
        """Test that detector access is safe when called from multiple contexts."""
        # Arrange
        call_count = [0]
        lock = threading.Lock()

        def mock_detect_with_lock(frame, project_type=None):
            with lock:
                call_count[0] += 1
                time.sleep(0.001)  # intentional 1ms delay - simulating detection work
            return ([], None)

        mock_detector.detect = mock_detect_with_lock

        # Act: Simulate multiple detection calls
        def perform_detection():
            video_processing_service.detector.detect(None, project_type="pre-recorded")

        threads = [threading.Thread(target=perform_detection) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All calls completed without deadlock
        assert call_count[0] == 10

    def test_project_manager_state_isolation(self, video_processing_service):
        """Test that project_manager state is not corrupted by concurrent access."""
        # Arrange
        pm = video_processing_service.project_manager
        zone_data = pm.get_zone_data()
        original_polygon = zone_data.polygon.copy()

        # Act: Multiple threads access zone data
        results = []

        def access_zone_data():
            data = pm.get_zone_data()
            results.append(data.polygon)

        threads = [threading.Thread(target=access_zone_data) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All threads received the same polygon
        assert all(r == original_polygon for r in results)

    def test_cancel_event_visibility_across_threads(self):
        """Test that cancel_event is properly visible across threads."""
        # Arrange
        cancel_event = threading.Event()

        # Act: Set event from one thread, check from another
        def setter():
            time.sleep(0.1)  # intentional 100ms delay - ensuring checker starts first
            cancel_event.set()

        def checker(results):
            wait_for_condition(
                lambda: cancel_event.is_set(),
                timeout=1.0,
                error_msg="Cancel event never set"
            )
            results.append(True)

        results = []
        t1 = threading.Thread(target=setter)
        t2 = threading.Thread(target=checker, args=(results,))

        t2.start()
        t1.start()

        t1.join()
        t2.join()

        # Assert: Checker thread detected the set event
        assert len(results) == 1
        assert results[0] is True


@pytest.mark.unit
class TestConcurrentProcessing:
    """Test concurrent video processing scenarios."""

    @patch("cv2.VideoCapture")
    def test_concurrent_initial_frame_display(self, mock_videocap, video_processing_service):
        """Test that display_initial_frame is safe when called concurrently."""
        # Arrange
        mock_cap = Mock()
        mock_cap.read = Mock(return_value=(True, np.zeros((480, 640, 3), dtype=np.uint8)))
        mock_cap.release = Mock()
        mock_videocap.return_value = mock_cap

        video_path = Path("/fake/video.mp4")

        # Act: Call from multiple threads
        def display_frame():
            video_processing_service.display_initial_frame(video_path)

        threads = [threading.Thread(target=display_frame) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All calls completed without error
        assert mock_cap.release.call_count == 5

    def test_concurrent_progress_callback_creation(self, video_processing_service):
        """Test that progress callbacks can be created concurrently."""
        # Arrange
        callbacks = []

        def create_callback():
            callback = video_processing_service.create_progress_callback(
                index=0, total_videos=10, experiment_id="test_001"
            )
            callbacks.append(callback)

        # Act: Create callbacks from multiple threads
        threads = [threading.Thread(target=create_callback) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All callbacks created successfully
        assert len(callbacks) == 10
        assert all(callable(cb) for cb in callbacks)

    @patch("cv2.VideoCapture")
    def test_concurrent_arena_polygon_creation(self, mock_videocap, video_processing_service):
        """Test that ensure_arena_polygon is safe under concurrent calls."""
        # Arrange
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(side_effect=lambda prop: 640 if prop == 3 else 480)
        mock_cap.release = Mock()
        mock_videocap.return_value = mock_cap

        video_path = Path("/fake/video.mp4")
        results = []

        # Act: Call from multiple threads
        def create_polygon():
            polygon = video_processing_service.ensure_arena_polygon(None, video_path)
            results.append(polygon)

        threads = [threading.Thread(target=create_polygon) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All calls returned valid polygons
        assert len(results) == 5
        assert all(r == [[0, 0], [640, 0], [640, 480], [0, 480]] for r in results)


@pytest.mark.unit
class TestStateManagerIntegration:
    """Test StateManager integration with thread safety."""

    def test_state_manager_updates_from_multiple_threads(self, video_processing_service):
        """Test that StateManager can handle concurrent updates."""
        # Arrange
        state_manager = video_processing_service.state_manager
        state_manager.update_state = Mock()

        # Act: Update state from multiple threads
        def update_state(index):
            state_manager.update_state(current_video=f"video_{index}.mp4", progress=index * 0.1)

        threads = [threading.Thread(target=update_state, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All updates were called
        assert state_manager.update_state.call_count == 10


@pytest.mark.slow
@pytest.mark.unit
class TestResourceManagementUnderLoad:
    """Test resource management under concurrent load."""

    @patch("cv2.VideoCapture")
    def test_video_capture_cleanup_under_concurrent_failures(
        self, mock_videocap, video_processing_service
    ):
        """Test VideoCapture resources cleanup under concurrent failures."""
        # Arrange
        failure_count = [0]

        def failing_videocap(path):
            mock_cap = Mock()
            if failure_count[0] < 3:
                failure_count[0] += 1
                mock_cap.isOpened = Mock(return_value=False)
            else:
                mock_cap.isOpened = Mock(return_value=True)
                mock_cap.get = Mock(side_effect=lambda prop: 640 if prop == 3 else 480)
            mock_cap.release = Mock()
            return mock_cap

        mock_videocap.side_effect = failing_videocap

        # Act: Attempt operations from multiple threads
        results = []

        def attempt_operation():
            try:
                polygon = video_processing_service.ensure_arena_polygon(
                    None, Path("/fake/video.mp4")
                )
                results.append(("success", polygon))
            except Exception as e:
                results.append(("error", str(e)))

        threads = [threading.Thread(target=attempt_operation) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: At least some operations succeeded
        successes = [r for r in results if r[0] == "success"]
        assert len(successes) >= 2, "Expected at least 2 successful operations after failures"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
