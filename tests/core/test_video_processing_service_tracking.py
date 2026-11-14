"""
Unit tests for VideoProcessingService - Tracking Workflow.

Tests run_tracking_if_needed, which hands the video to ProcessingWorker, and
the video-context helpers. The frame loop itself is covered by the worker's
tests (tests/core/test_processing_worker_unit.py and the pre-recorded golden).
"""

import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.video.video_processing_service import VideoProcessingService


@pytest.fixture
def mock_services():
    """Create all mocked service dependencies."""
    settings = SimpleNamespace(video_processing=SimpleNamespace(fps=30.0))
    return {
        "detector": Mock(),
        "recorder": Mock(),
        "project_manager": Mock(),
        "state_manager": Mock(),
        "ui_coordinator": Mock(),
        "ui_event_bus": Mock(),
        "cancel_event": threading.Event(),
        "settings_obj": settings,
    }


@pytest.fixture
def video_processing_service(mock_services):
    """Create VideoProcessingService with mocked dependencies."""
    service = VideoProcessingService(**mock_services)
    return service


class TestRunTrackingIfNeeded:
    """Test suite for run_tracking_if_needed method."""

    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_skips_existing_trajectory(self, mock_exists, video_processing_service):
        """Test that existing trajectory file skips tracking generation."""
        mock_exists.return_value = True  # Trajectory already exists
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        # Should return success without running detection
        assert success is True
        assert polygon is not None

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_returns_false_when_detector_none(
        self, mock_exists, mock_worker, video_processing_service
    ):
        """Test that missing detector returns False."""
        mock_exists.return_value = False  # No existing trajectory
        video_processing_service.detector = None
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        assert success is False
        assert polygon is not None

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.log")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_processes_video_frames(
        self, mock_exists, mock_log, mock_worker, video_processing_service
    ):
        """Test that worker is started with correct configuration."""
        mock_exists.return_value = False

        # Setup mocks
        mock_worker_instance = mock_worker.return_value
        mock_thread = Mock()
        mock_worker_instance.start_in_thread.return_value = mock_thread

        # Setup project manager
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480]])
        )

        _success, _polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=1,
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # Verify worker creation
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        context = args[0]

        # Verify context
        assert context.analysis_interval_frames == 1
        assert context.videos_to_process[0]["experiment_id"] == "test_001"
        # The weight is resolved in the main process and shipped (ADR-009).
        assert context.model_spec is not None

        # Verify worker started
        mock_worker_instance.start_in_thread.assert_called_once()
        mock_thread.join.assert_called_once()

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_ships_the_project_weight_to_the_worker(
        self, mock_exists, mock_worker, video_processing_service, tmp_path
    ):
        """Re-tracking a project video must load the PROJECT's weight."""
        mock_exists.return_value = False
        rat = tmp_path / "best_det_topdown_rat_v1.pt"
        rat.write_bytes(b"rat")
        weight_manager = Mock()
        weight_manager.weights = {rat.name: {"path": str(rat), "type": "det"}}
        weight_manager.get_weight_sha256.return_value = "c" * 64
        video_processing_service.weight_manager = weight_manager
        video_processing_service.project_manager.project_data = {
            "model_overrides": {"slot_weights": {"det:zebrafish": rat.name}},
            "model_selection": {"animal_method": "det"},
            "use_openvino": False,
        }
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480]])
        )

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        context = mock_worker.call_args.args[0]
        assert context.model_spec.model_path == str(rat)
        assert context.model_spec.weight_sha256 == "c" * 64

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_respects_analysis_interval(self, mock_exists, mock_worker, video_processing_service):
        """Test that analysis_interval_frames is passed to worker context."""
        mock_exists.return_value = False

        # Setup mocks
        mock_worker_instance = mock_worker.return_value
        mock_worker_instance.start_in_thread.return_value = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=5,  # Process every 5th frame
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # Verify context has correct interval
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        context = args[0]
        assert context.analysis_interval_frames == 5

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_handles_cancellation(self, mock_exists, mock_worker, video_processing_service):
        """Test that cancel event is passed to worker context."""
        mock_exists.return_value = False

        mock_worker_instance = mock_worker.return_value
        mock_worker_instance.start_in_thread.return_value = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        # Verify context has cancel event
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        context = args[0]
        assert context.cancel_event == video_processing_service.cancel_event

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_includes_calibration_data(self, mock_exists, mock_worker, video_processing_service):
        """Test that zone data is passed to worker context."""
        mock_exists.return_value = False

        mock_worker_instance = mock_worker.return_value
        mock_worker_instance.start_in_thread.return_value = Mock()

        mock_zone_data = Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        video_processing_service.project_manager.get_zone_data = Mock(return_value=mock_zone_data)

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        # Verify context has zone data
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        context = args[0]
        assert context.zone_data == mock_zone_data

    @patch("zebtrack.core.video.processing_worker.ProcessingWorker")
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    def test_calls_progress_callback(self, mock_exists, mock_worker, video_processing_service):
        """Test that progress callback is wired correctly."""
        mock_exists.return_value = False

        mock_worker_instance = mock_worker.return_value
        mock_worker_instance.start_in_thread.return_value = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        progress_callback = Mock()

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            progress_callback=progress_callback,
        )

        # Verify callbacks created and passed
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        callbacks = args[1]

        # Simulate worker calling on_progress
        callbacks.on_progress(0.5, "Processing", {})

        # Verify progress_callback called
        progress_callback.assert_called_once_with(0.5, "Processing", stats={})


class FakeCap:
    """Simple fake VideoCapture for helper tests."""

    def __init__(self, width=320, height=240, fps=25.0, read_success=True):
        self.width = width
        self.height = height
        self.fps = fps
        self.read_success = read_success
        self.set_calls = []
        self.grab_calls = 0
        self.position = 0

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return 200
        if prop == cv2.CAP_PROP_POS_MSEC:
            return 1000.0
        return 0

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        if prop == cv2.CAP_PROP_POS_FRAMES:
            self.position = value
        return True

    def grab(self):
        self.grab_calls += 1
        return True

    def read(self):
        return self.read_success, np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def release(self):
        return True


class TestVideoContextHelpers:
    """Coverage for helper paths in VideoProcessingService."""

    @patch(
        "zebtrack.core.video.video_context_factory.time.perf_counter",
        side_effect=[0.0, 0.001],
    )
    @patch("zebtrack.core.video.video_context_factory.cv2.VideoCapture")
    def test_create_video_context_calibrates_skip_threshold(
        self, mock_videocap, mock_perf, video_processing_service
    ):
        fake_cap = FakeCap()
        mock_videocap.return_value = fake_cap

        ctx = video_processing_service._create_video_context("/tmp/fake.mp4")

        assert ctx is not None
        assert ctx.width == fake_cap.width
        assert ctx.height == fake_cap.height
        assert ctx.skip_threshold == 120  # fast seek path
        assert ctx.first_frame is not None

    def test_seek_to_frame_strategies(self, video_processing_service):
        backward_cap = FakeCap()
        video_processing_service._seek_to_frame(backward_cap, target_frame=0, current_frame=5)
        assert backward_cap.set_calls[-1][1] == 0

        small_gap_cap = FakeCap()
        video_processing_service._seek_to_frame(
            small_gap_cap, target_frame=3, current_frame=0, skip_threshold=5
        )
        assert small_gap_cap.grab_calls == 3

        large_gap_cap = FakeCap()
        video_processing_service._seek_to_frame(
            large_gap_cap, target_frame=100, current_frame=0, skip_threshold=10
        )
        assert large_gap_cap.set_calls[-1] == (cv2.CAP_PROP_POS_FRAMES, 100)

    def test_load_trajectory_dataframe_missing_publishes_event(
        self, video_processing_service, tmp_path
    ):
        video_processing_service.ui_event_bus.publish = Mock()
        missing_path = tmp_path / "missing.parquet"

        result = video_processing_service.load_trajectory_dataframe(missing_path, "exp-1")

        assert result is None
        video_processing_service.ui_event_bus.publish.assert_called_once()

    def test_load_trajectory_dataframe_read_failure(
        self, video_processing_service, tmp_path, monkeypatch
    ):
        video_processing_service.ui_event_bus.publish = Mock()
        bad_path = tmp_path / "bad.parquet"
        bad_path.write_text("not_parquet")

        monkeypatch.setattr(
            "zebtrack.core.video.video_context_factory.pd.read_parquet",
            Mock(side_effect=ValueError("boom")),
        )

        result = video_processing_service.load_trajectory_dataframe(bad_path, "exp-2")

        assert result is None
        video_processing_service.ui_event_bus.publish.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
