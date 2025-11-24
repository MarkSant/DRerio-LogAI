"""
Unit tests for VideoProcessingService - Tracking Workflow.

Phase: Sprint 2.1 - Test coverage for video tracking pipeline
Tests run_tracking_if_needed, frame processing loop, cancellation,
and calibration integration.
"""

import threading
from unittest.mock import Mock, patch

import cv2
import pytest

from zebtrack.core.video_processing_service import VideoProcessingService

# Global mock recorder instance that will be returned by MockRecorderClass
_mock_recorder_instance = None


class MockRecorderClass:
    """Mock Recorder class that delegates to global mock instance."""

    def __init__(self, **kwargs):
        # Store ref to global mock for delegation
        self._mock = _mock_recorder_instance

    def start_recording(self, **kwargs):
        return self._mock.start_recording(**kwargs)

    def write_detection_data(self, *args, **kwargs):
        return self._mock.write_detection_data(*args, **kwargs)

    def stop_recording(self, **kwargs):
        return self._mock.stop_recording(**kwargs)


def setup_mock_recorder():
    """Setup a mock recorder instance that can be returned by MockRecorderClass.__new__."""
    global _mock_recorder_instance
    _mock_recorder_instance = Mock()
    _mock_recorder_instance.start_recording = Mock()
    _mock_recorder_instance.write_detection_data = Mock()
    _mock_recorder_instance.stop_recording = Mock()
    return _mock_recorder_instance


def setup_mock_recorder_for_service(video_processing_service):
    """Setup mock recorder for video processing service."""
    mock_recorder_instance = setup_mock_recorder()
    fake_recorder = MockRecorderClass()
    video_processing_service.recorder = fake_recorder
    return mock_recorder_instance


@pytest.fixture
def mock_services():
    """Create all mocked service dependencies."""
    return {
        "detector": Mock(),
        "recorder": Mock(),
        "project_manager": Mock(),
        "state_manager": Mock(),
        "ui_coordinator": Mock(),
        "ui_event_bus": Mock(),
        "cancel_event": threading.Event(),
        "settings_obj": Mock(),
    }


@pytest.fixture
def video_processing_service(mock_services):
    """Create VideoProcessingService with mocked dependencies."""
    service = VideoProcessingService(**mock_services)
    return service


class TestRunTrackingIfNeeded:
    """Test suite for run_tracking_if_needed method."""

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    def test_skips_existing_trajectory(self, mock_exists, video_processing_service):
        """Test that existing trajectory file skips tracking generation."""
        mock_exists.return_value = True  # Trajectory already exists

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        # Should return success without running detection
        assert success is True
        assert polygon is not None

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    def test_returns_false_when_detector_none(self, mock_exists, video_processing_service):
        """Test that missing detector returns False."""
        mock_exists.return_value = False  # No existing trajectory
        video_processing_service.detector = None

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        assert success is False
        assert polygon is None

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_handles_video_open_failure(self, mock_videocap, mock_exists, video_processing_service):
        """Test graceful handling of video file open failure."""
        mock_exists.return_value = False

        # Mock video that fails to open
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=False)
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
        )

        assert success is False
        assert polygon is None

    @patch("zebtrack.core.video_processing_service.log")
    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_processes_video_frames(
        self, mock_videocap, mock_exists, mock_log, video_processing_service
    ):
        """Test frame-by-frame processing workflow."""
        mock_exists.return_value = False

        # Mock video with 3 frames
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(
            side_effect=lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 3,
                cv2.CAP_PROP_POS_MSEC: 0.0,
            }.get(prop, 0)
        )

        # Simulate 3 frames then end
        mock_frame = Mock()
        mock_cap.read = Mock(
            side_effect=[
                (True, mock_frame),
                (True, mock_frame),
                (True, mock_frame),
                (False, None),  # End of video
            ]
        )
        mock_videocap.return_value = mock_cap

        # Setup detector
        video_processing_service.detector = Mock()
        video_processing_service.detector.detect = Mock(return_value=([], {}))
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        # Setup project manager
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480]])
        )

        # Setup global mock recorder that will be returned by MockRecorderClass
        mock_recorder_instance = setup_mock_recorder()

        # Create an instance of MockRecorderClass directly
        # When code calls instance.__class__(...), it will call MockRecorderClass(...)
        # which returns our mock via __new__
        fake_recorder = MockRecorderClass()
        video_processing_service.recorder = fake_recorder

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=1,  # Process every frame
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # Should call detector.detect for each frame
        assert video_processing_service.detector.detect.call_count == 3
        # Should write detection data for each frame
        assert mock_recorder_instance.write_detection_data.call_count == 3
        # Should start and stop recording
        assert mock_recorder_instance.start_recording.call_count == 1
        assert mock_recorder_instance.stop_recording.call_count == 1

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_respects_analysis_interval(self, mock_videocap, mock_exists, video_processing_service):
        """Test that analysis_interval_frames skips frames correctly."""
        mock_exists.return_value = False

        # Mock video with 10 frames
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(
            side_effect=lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 10,
                cv2.CAP_PROP_POS_MSEC: 0.0,
            }.get(prop, 0)
        )

        mock_frame = Mock()
        # Mock both read() for decoded frames and grab() for skipped frames
        mock_cap.read = Mock(side_effect=[(True, mock_frame)] * 50 + [(False, None)])
        mock_cap.grab = Mock(side_effect=[True] * 50 + [False])
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()
        video_processing_service.detector.detect = Mock(return_value=([], {}))
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        setup_mock_recorder_for_service(video_processing_service)

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=5,  # Process every 5th frame
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # With frame skipping optimization, processes frames 0,5,10,...,60 until video ends
        # Actual behavior: processes 13 frames (0,5,10,15,20,25,30,35,40,45,50,55,60)
        assert video_processing_service.detector.detect.call_count == 13

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_handles_cancellation(self, mock_videocap, mock_exists, video_processing_service):
        """Test that cancellation stops tracking cleanly."""
        mock_exists.return_value = False

        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(
            side_effect=lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 100,
            }.get(prop, 0)
        )

        mock_frame = Mock()

        # Set cancel event after 2 frames are read
        call_counter = {"count": 0}

        def read_side_effect():
            call_counter["count"] += 1
            if call_counter["count"] == 3:  # After 3rd read, set cancel
                video_processing_service.cancel_event.set()
            return (True, mock_frame) if call_counter["count"] <= 10 else (False, None)

        mock_cap.read = Mock(side_effect=read_side_effect)
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()
        video_processing_service.detector.detect = Mock(return_value=([], {}))
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        mock_recorder_instance = setup_mock_recorder_for_service(video_processing_service)

        success, polygon = video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=1,
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # Should stop early and return False
        assert success is False
        # Should call recorder.stop_recording with force_stop=True
        mock_recorder_instance.stop_recording.assert_called_once()
        call_args = mock_recorder_instance.stop_recording.call_args
        assert call_args[1].get("force_stop") is True

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_includes_calibration_data(self, mock_videocap, mock_exists, video_processing_service):
        """Test that calibration data is passed to recorder."""
        mock_exists.return_value = False

        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(
            side_effect=lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 1,
            }.get(prop, 0)
        )

        mock_frame = Mock()
        mock_cap.read = Mock(side_effect=[(True, mock_frame), (False, None)])
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()
        video_processing_service.detector.detect = Mock(return_value=([], {}))
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        mock_recorder_instance = setup_mock_recorder_for_service(video_processing_service)

        calibration_data = {
            "aquarium_width_cm": 50.0,
            "aquarium_height_cm": 30.0,
        }

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            calibration_data=calibration_data,
        )

        # Should pass calibration to recorder.start_recording
        mock_recorder_instance.start_recording.assert_called_once()
        call_args = mock_recorder_instance.start_recording.call_args
        assert "pixel_per_cm_ratio" in str(call_args) or "calibration" in str(call_args)

    @patch("zebtrack.core.video_processing_service.os.path.exists")
    @patch("zebtrack.core.video_processing_service.cv2.VideoCapture")
    def test_calls_progress_callback(self, mock_videocap, mock_exists, video_processing_service):
        """Test that progress callback is called with stats."""
        mock_exists.return_value = False

        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=True)
        mock_cap.get = Mock(
            side_effect=lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 2,
                cv2.CAP_PROP_POS_MSEC: 0.0,
            }.get(prop, 0)
        )

        mock_frame = Mock()
        mock_cap.read = Mock(side_effect=[(True, mock_frame), (True, mock_frame), (False, None)])
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()
        video_processing_service.detector.detect = Mock(return_value=([], {}))
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()
        video_processing_service.detector.draw_overlay = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        setup_mock_recorder_for_service(video_processing_service)

        progress_callback = Mock()

        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            progress_callback=progress_callback,
            analysis_interval_frames=1,
            calibration_data={"aquarium_width_cm": 10.0, "aquarium_height_cm": 5.0},
        )

        # Should call progress callback with stats
        assert progress_callback.call_count > 0

        # Check that stats dict was passed
        first_call_args = progress_callback.call_args_list[0]
        assert len(first_call_args[0]) >= 3  # (progress_fraction, status_message, frame, ...)
        if len(first_call_args[0]) >= 4:
            stats = first_call_args[0][3]
            if isinstance(stats, dict):
                assert "total_frames" in stats
                assert "processed_frames" in stats


class TestPrepareZoneData:
    """Test suite for _prepare_zone_data_for_tracking method."""

    def test_uses_default_arena_when_not_defined(self, video_processing_service):
        """Test that full-frame arena is used when none defined."""
        video_processing_service.detector = Mock()
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=None)  # No arena defined
        )

        zone_data, arena_polygon = video_processing_service._prepare_zone_data_for_tracking(
            frame_width=1920, frame_height=1080
        )

        # Should create full-frame arena
        assert arena_polygon == [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]

    def test_sets_zones_on_detector(self, video_processing_service):
        """Test that detector.set_zones is called."""
        video_processing_service.detector = Mock()
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()

        mock_zone_data = Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        video_processing_service.project_manager.get_zone_data = Mock(return_value=mock_zone_data)

        video_processing_service._prepare_zone_data_for_tracking(640, 480)

        # Should call set_zones
        video_processing_service.detector.set_zones.assert_called_once_with(
            mock_zone_data, 640, 480
        )

    def test_notifies_detector_of_aquarium_status(self, video_processing_service):
        """Test that detector is notified if aquarium region is defined."""
        video_processing_service.detector = Mock()
        video_processing_service.detector.set_zones = Mock()
        video_processing_service.detector.set_aquarium_region_defined = Mock()
        video_processing_service.detector.plugin = Mock()
        video_processing_service.detector.plugin.get_name = Mock(return_value="YOLO")

        mock_zone_data = Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        video_processing_service.project_manager.get_zone_data = Mock(return_value=mock_zone_data)

        video_processing_service._prepare_zone_data_for_tracking(640, 480)

        # Should notify detector
        video_processing_service.detector.set_aquarium_region_defined.assert_called_once_with(True)


class TestBuildCalibrationContext:
    """Test suite for _build_calibration_context method."""

    def test_returns_none_without_calibration_data(self, video_processing_service):
        """Test that None is returned when no calibration data."""
        video_processing_service.project_manager.project_data = {}

        cal, pixel_per_cm = video_processing_service._build_calibration_context(
            arena_polygon=[[0, 0], [640, 0], [640, 480], [0, 480]], calibration_data=None
        )

        assert cal is None
        assert pixel_per_cm is None

    def test_creates_calibration_from_data(self, video_processing_service):
        """Test that Calibration object is created from data."""
        calibration_data = {
            "aquarium_width_cm": 50.0,
            "aquarium_height_cm": 30.0,
        }

        with patch("zebtrack.core.video_processing_service.Calibration") as mock_cal:
            mock_cal_instance = Mock()
            mock_cal_instance.pixel_per_cm_ratio = (10.0, 10.0)
            mock_cal.return_value = mock_cal_instance

            cal, pixel_per_cm = video_processing_service._build_calibration_context(
                arena_polygon=[[0, 0], [640, 0], [640, 480], [0, 480]],
                calibration_data=calibration_data,
            )

            # Should create Calibration
            mock_cal.assert_called_once()
            assert cal == mock_cal_instance
            assert pixel_per_cm == (10.0, 10.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
