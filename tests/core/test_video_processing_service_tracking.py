"""
Unit tests for VideoProcessingService - Tracking Workflow.

Tests run_tracking_if_needed, which hands the video to ProcessingWorker, and
the video-context helpers. The frame loop itself is covered by the worker's
tests (tests/core/test_processing_worker_unit.py and the pre-recorded golden).
"""

import threading
from pathlib import Path
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
    def test_preview_frames_carry_the_workers_roles(
        self, mock_exists, mock_worker, video_processing_service
    ):
        """#645: the single-video preview draws with the worker's role map."""
        mock_exists.return_value = False
        mock_worker.return_value.start_in_thread.return_value = Mock()
        video_processing_service.project_manager.get_zone_data = Mock(
            return_value=ZoneData(polygon=[[0, 0], [640, 0], [640, 480]])
        )
        video_processing_service.run_tracking_if_needed(
            video_path="/fake/video.mp4",
            results_dir="/fake/results",
            experiment_id="test_001",
            analysis_interval_frames=1,
        )
        callbacks = mock_worker.call_args.args[1]
        bus = video_processing_service.ui_event_bus
        bus.publish.reset_mock()

        callbacks.on_frame_processed("frame", [(0, 0, 1, 1)], {"class_roles": {1: "context"}})
        callbacks.on_frame_processed("frame", [], {"fps": 3.0})

        shown = [c.args[0].data.class_roles for c in bus.publish.call_args_list]
        assert shown == [{1: "context"}, None]

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


# ---------------------------------------------------------------------------
# run_tracking_if_needed with a scripted worker (TASK-087)
# ---------------------------------------------------------------------------


class _ScriptedWorker:
    """``ProcessingWorker`` stand-in: replays a script through the callbacks."""

    script: tuple = ()  # callables taking the callbacks
    instances: list = []  # noqa: RUF012 - test double, reset by the fixture

    def __init__(self, context, callbacks):
        self.context = context
        self.callbacks = callbacks
        type(self).instances.append(self)

    def start_in_thread(self):
        def play():
            for step in type(self).script:
                step(self.callbacks)

        thread = threading.Thread(target=play, daemon=True)
        thread.start()
        return thread


@pytest.fixture
def scripted(monkeypatch):
    from zebtrack.core.video import processing_worker

    _ScriptedWorker.script = ()
    _ScriptedWorker.instances = []
    monkeypatch.setattr(processing_worker, "ProcessingWorker", _ScriptedWorker)
    return _ScriptedWorker


def _track(service, tmp_path, **kw):
    service.project_manager.get_zone_data = Mock(
        return_value=ZoneData(polygon=[(0, 0), (640, 0), (640, 480)])
    )
    return service.run_tracking_if_needed(
        kw.pop("video_path", "/fake/video.mp4"),
        tmp_path,
        kw.pop("experiment_id", "E1"),
        **kw,
    )


def _published(service):
    return [call.args[0] for call in service.ui_event_bus.publish.call_args_list]


class TestRunTrackingWithScriptedWorker:
    def test_an_existing_trajectory_short_circuits_before_any_worker(
        self, video_processing_service, tmp_path, scripted
    ):
        (tmp_path / "3_CoordMovimento_E1.parquet").write_bytes(b"")

        ok, polygon = _track(video_processing_service, tmp_path)

        assert ok is True
        # The polygon comes back as plain lists, whatever the zone stored.
        assert polygon == [[0, 0], [640, 0], [640, 480]]
        assert scripted.instances == []
        assert _published(video_processing_service) == []

    def test_the_worker_gets_the_run_configuration_and_a_status_is_published(
        self, video_processing_service, tmp_path, scripted
    ):
        from zebtrack.ui.event_bus_v2 import UIEvents

        ok, polygon = _track(
            video_processing_service,
            tmp_path,
            analysis_interval_frames=4,
            display_interval_frames=2,
        )

        assert ok is False  # the script never reports a completed video
        assert polygon == [[0, 0], [640, 0], [640, 480]]
        (worker,) = scripted.instances
        context = worker.context
        assert context.videos_to_process == [
            {"path": str(Path("/fake/video.mp4")), "experiment_id": "E1"}
        ]
        assert context.output_base_dir == str(tmp_path)
        assert (context.analysis_interval_frames, context.display_interval_frames) == (4, 2)
        assert context.cancel_event is video_processing_service.cancel_event
        assert context.single_video_config is None
        (event,) = _published(video_processing_service)
        assert event.type == UIEvents.SET_STATUS
        assert event.data.message == "Starting process for E1..."

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (SimpleNamespace(video_path="/clips/a.mp4"), "/clips/a.mp4"),
            (SimpleNamespace(camera_index=2), "2"),
            (
                SimpleNamespace(get_properties=lambda: {"is_live_stream": True, "camera_index": 3}),
                "3",
            ),
            (SimpleNamespace(get_properties=lambda: {"is_live_stream": True}), "0"),
            (SimpleNamespace(get_properties=lambda: {"path": "/clips/b.mp4"}), "/clips/b.mp4"),
        ],
    )
    def test_the_worker_task_path_is_resolved_from_a_frame_source(
        self, video_processing_service, tmp_path, scripted, source, expected
    ):
        _track(video_processing_service, tmp_path, video_path=source)
        assert scripted.instances[0].context.videos_to_process[0]["path"] == expected

    def test_a_frame_source_whose_properties_fail_keeps_its_string_form(
        self, video_processing_service, tmp_path, scripted
    ):
        def broken():
            raise AttributeError("no properties")

        source = SimpleNamespace(get_properties=broken)
        _track(video_processing_service, tmp_path, video_path=source)
        assert scripted.instances[0].context.videos_to_process[0]["path"] == str(source)

    def test_a_properties_dict_without_path_keeps_the_string_form(
        self, video_processing_service, tmp_path, scripted
    ):
        source = SimpleNamespace(get_properties=lambda: {"fps": 30})
        _track(video_processing_service, tmp_path, video_path=source)
        assert scripted.instances[0].context.videos_to_process[0]["path"] == str(source)

    def test_progress_is_forwarded_with_the_three_field_shape(
        self, video_processing_service, tmp_path, scripted
    ):
        seen = []

        def progress(fraction, message, stats=None):
            seen.append((fraction, message, stats))

        scripted.script = (
            lambda cb: cb.on_progress(0.25, "tracking", {"fps": 9}),
            # The worker's own six-field shape: index, total, id, fraction, message, stats.
            lambda cb: cb.on_progress(1, 4, "E1", 0.5, "halfway", None),
            # Neither shape: dropped with a warning instead of crashing the monitor.
            lambda cb: cb.on_progress(0.9, "bad"),
        )

        _track(video_processing_service, tmp_path, progress_callback=progress)

        assert seen == [(0.25, "tracking", {"fps": 9}), (0.5, "halfway", None)]

    def test_progress_without_a_callback_is_ignored(
        self, video_processing_service, tmp_path, scripted
    ):
        scripted.script = (lambda cb: cb.on_progress(0.25, "tracking", None),)
        ok, _ = _track(video_processing_service, tmp_path)
        assert ok is False

    def test_frames_become_display_events_and_empty_frames_do_not(
        self, video_processing_service, tmp_path, scripted
    ):
        from zebtrack.ui.event_bus_v2 import UIEvents

        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        scripted.script = (
            lambda cb: cb.on_frame_processed(frame, [(1, 2, 3, 4, 0.9, 5, 1)], {}),
            lambda cb: cb.on_frame_processed(frame, None, {"class_roles": {1: "subject"}}),
            lambda cb: cb.on_frame_processed(None, [(1, 2, 3, 4, 0.9, 5, 1)], {}),
        )

        _track(video_processing_service, tmp_path)

        shown = [
            e for e in _published(video_processing_service) if e.type == UIEvents.UI_DISPLAY_FRAME
        ]
        assert len(shown) == 2
        assert shown[0].data.detections == [(1, 2, 3, 4, 0.9, 5, 1)]
        assert shown[0].data.class_roles is None
        assert shown[1].data.detections == []
        assert shown[1].data.class_roles == {1: "subject"}

    @pytest.mark.parametrize("success", [True, False])
    def test_the_result_is_what_the_worker_reported_for_the_video(
        self, video_processing_service, tmp_path, scripted, success
    ):
        scripted.script = (lambda cb: cb.on_video_completed(0, 1, "E1", success),)
        ok, _ = _track(video_processing_service, tmp_path)
        assert ok is success

    def test_the_last_completion_wins(self, video_processing_service, tmp_path, scripted):
        scripted.script = (
            lambda cb: cb.on_video_completed(0, 1, "E1", True),
            lambda cb: cb.on_video_completed(0, 1, "E1", False),
        )
        ok, _ = _track(video_processing_service, tmp_path)
        assert ok is False

    def test_the_remaining_callbacks_only_log(self, video_processing_service, tmp_path, scripted):
        scripted.script = (
            lambda cb: cb.on_started(),
            lambda cb: cb.on_error(RuntimeError("x"), "E1"),
            lambda cb: cb.on_completed(False, "out", None),
            lambda cb: cb.on_fatal_error(RuntimeError("y"), "ctx", {}),
        )
        ok, _ = _track(video_processing_service, tmp_path)
        assert ok is False
