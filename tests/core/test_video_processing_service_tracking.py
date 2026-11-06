"""
Unit tests for VideoProcessingService - Tracking Workflow.

Phase: Sprint 2.1 - Test coverage for video tracking pipeline
Tests run_tracking_if_needed, frame processing loop, cancellation,
and calibration integration.
"""

import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.video.video_processing_service import VideoProcessingService
from zebtrack.ui.event_bus_v2 import UIEvents

# Global mock recorder instance that will be returned by MockRecorderClass
_mock_recorder_instance: Any | None = None


class MockRecorderClass:
    """Mock Recorder class that delegates to global mock instance."""

    def __init__(self, **kwargs):
        # Store ref to global mock for delegation
        self._mock = cast(Mock, _mock_recorder_instance)
        assert self._mock is not None

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
    @patch("zebtrack.core.video.tracking_session_runner.os.path.exists")
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_handles_video_open_failure(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service
    ):
        """Test graceful handling of video file open failure."""
        mock_exists.return_value = False

        # Mock video that fails to open
        mock_cap = Mock()
        mock_cap.isOpened = Mock(return_value=False)
        mock_videocap.return_value = mock_cap

        video_processing_service.detector = Mock()
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_processes_video_frames(
        self, mock_videocap, mock_exists, mock_log, mock_worker, video_processing_service
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_ships_the_project_weight_to_the_worker(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service, tmp_path
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_respects_analysis_interval(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service
    ):
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_handles_cancellation(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service
    ):
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_includes_calibration_data(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service
    ):
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
    @patch("zebtrack.core.video.tracking_session_runner.cv2.VideoCapture")
    def test_calls_progress_callback(
        self, mock_videocap, mock_exists, mock_worker, video_processing_service
    ):
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

        _zone_data, arena_polygon = video_processing_service._prepare_zone_data_for_tracking(
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

        with patch("zebtrack.core.video.tracking_session_runner.Calibration") as mock_cal:
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

    def test_finalize_tracking_session_handles_cancel(self, video_processing_service):
        recorder = Mock()

        success, arena = video_processing_service._finalize_tracking_session(
            recorder=recorder,
            cancel_requested=True,
            experiment_id="exp-3",
            trajectory_path="traj",
            arena_polygon=[[0, 0], [1, 1], [1, 0]],
        )

        assert success is False
        assert arena == [[0, 0], [1, 1], [1, 0]]
        recorder.stop_recording.assert_called_once_with(force_stop=True, reason="Cancelled by user")
        video_processing_service.ui_event_bus.publish.assert_called_once()
        call_ev = video_processing_service.ui_event_bus.publish.call_args[0][0]
        assert call_ev.type == UIEvents.SET_STATUS
        assert "Cancellation" in call_ev.data.message

    @patch("zebtrack.core.video.tracking_session_runner.time.time", return_value=15.0)
    def test_calculate_tracking_progress_stats(self, mock_time, video_processing_service):
        cap = FakeCap()

        progress, stats = video_processing_service._calculate_tracking_progress_stats(
            frame_num=99,
            processed_frames_count=50,
            detected_frames_count=10,
            start_time=10.0,
            cap=cap,
        )

        assert progress == 0.5
        assert stats["current_frame"] == 100
        assert stats["eta"] == pytest.approx(5.0)


class _ObservingDetector:
    """Detector double: no subject detection, one context observation."""

    def __init__(self):
        self.popped = 0

    def detect(self, frame, project_type=None):
        return [], None

    def pop_class_observations(self):
        self.popped += 1
        return [
            {
                "class_id": 2,
                "class_name": "experimenter",
                "role": "context",
                "bbox": (1.0, 2.0, 3.0, 4.0),
                "confidence": 0.8,
                "aquarium_id": None,
            }
        ]


class TestInProcessObjectSidecar:
    """``_process_tracking_frame`` feeds the ``3c_Objetos_`` sidecar (ADR-010)."""

    def _recorder(self, persist):
        recorder = Mock()
        recorder.persist_object_sidecar = persist
        recorder.persist_masks = False
        return recorder

    def test_processed_frame_without_detection_still_gets_its_heartbeat(
        self, video_processing_service
    ):
        recorder = self._recorder(True)
        detector = _ObservingDetector()

        detections, increment, processed = video_processing_service._process_tracking_frame(
            frame=np.zeros((4, 4, 3), dtype=np.uint8),
            frame_num=6,
            analysis_interval_frames=3,
            cap=FakeCap(),
            recorder=recorder,
            detector=detector,
        )

        assert (detections, increment, processed) == ([], 0, True)
        recorder.write_object_data.assert_called_once()
        args = recorder.write_object_data.call_args.args
        # timestamp == t_event_s == PTS (FakeCap reports 1000 ms).
        assert args[:3] == (1.0, 6, 1.0)
        assert [item["role"] for item in args[3]] == ["context"]

    def test_skipped_frame_writes_nothing(self, video_processing_service):
        recorder = self._recorder(True)
        detector = _ObservingDetector()

        video_processing_service._process_tracking_frame(
            frame=np.zeros((4, 4, 3), dtype=np.uint8),
            frame_num=7,
            analysis_interval_frames=3,
            cap=FakeCap(),
            recorder=recorder,
            detector=detector,
        )

        recorder.write_object_data.assert_not_called()
        assert detector.popped == 0

    def test_kill_switch_writes_nothing(self, video_processing_service):
        recorder = self._recorder(False)
        detector = _ObservingDetector()

        video_processing_service._process_tracking_frame(
            frame=np.zeros((4, 4, 3), dtype=np.uint8),
            frame_num=0,
            analysis_interval_frames=1,
            cap=FakeCap(),
            recorder=recorder,
            detector=detector,
        )

        recorder.write_object_data.assert_not_called()

    def test_setup_passes_the_object_metadata_to_the_recorder(
        self, video_processing_service, tmp_path
    ):
        from zebtrack.core.detection.class_roles import resolve_class_role_map

        started = {}

        class _Recorder:
            def __init__(self, settings_obj=None):
                pass

            def start_recording(self, **kwargs):
                started.update(kwargs)
                return True

        detector = Mock()
        detector.class_role_map = resolve_class_role_map(
            {0: "arena", 1: "rat"}, weight_sha256="cd" * 32
        )
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [320, 0], [320, 240], [0, 240]])
        )
        video_processing_service.project_manager.project_data = {}

        with patch(
            "zebtrack.core.video.tracking_session_runner.cv2.VideoCapture", return_value=FakeCap()
        ):
            video_processing_service._setup_tracking_session(
                video_path=tmp_path / "v.mp4",
                results_dir=tmp_path,
                experiment_id="exp",
                calibration_data=None,
                recorder=_Recorder(),
                detector=detector,
            )

        metadata = started["object_metadata"]
        assert metadata.clock == "pts"
        assert metadata.class_names == {0: "arena", 1: "rat"}
        assert metadata.weight_sha256 == "cd" * 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestInProcessFrameClock:
    """``_process_tracking_frame`` hands ByteTrack the frame's PTS (#654)."""

    def test_the_pts_is_declared_before_the_frame_is_detected(self, video_processing_service):
        calls: list[tuple[str, float | None]] = []

        class _ClockDetector:
            def set_frame_time(self, t_s):
                calls.append(("set_frame_time", t_s))

            def detect(self, frame, project_type=None):
                calls.append(("detect", None))
                return [], None

        recorder = Mock()
        recorder.persist_object_sidecar = False
        recorder.persist_masks = False

        video_processing_service._process_tracking_frame(
            frame=np.zeros((4, 4, 3), dtype=np.uint8),
            frame_num=3,
            analysis_interval_frames=3,
            cap=FakeCap(),  # reports 1000 ms
            recorder=recorder,
            detector=_ClockDetector(),
        )

        assert calls == [("set_frame_time", 1.0), ("detect", None)]
        # The row is dated on the same clock.
        assert recorder.write_detection_data.call_args.args[0] == 1.0
