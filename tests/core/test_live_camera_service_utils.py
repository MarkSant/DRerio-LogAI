"""Unit tests for LiveCameraService helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from zebtrack.core.recording import camera_connection_handler as camera_conn_module
from zebtrack.core.recording.live_camera_service import LiveCameraService


@pytest.fixture
def live_camera_service():
    """Create LiveCameraService with mocked dependencies."""
    return LiveCameraService(
        controller=None,
        state_manager=Mock(),
        project_manager=Mock(),
        recording_service=Mock(),
        detector_service=Mock(),
        settings_obj=Mock(),
        recorder=Mock(),
        event_bus=Mock(),
        root=None,
    )


def test_resolve_calibration_perspective_returns_top_down(live_camera_service):
    """When project_data carries calibration.behavioral_analysis.aquarium_perspective,
    the helper must surface it so live can pick the correct 4-slot default.
    """
    pm = Mock()
    pm.project_data = {"calibration": {"behavioral_analysis": {"aquarium_perspective": "top_down"}}}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() == "top_down"


def test_resolve_calibration_perspective_returns_lateral(live_camera_service):
    """Lateral perspective must round-trip unchanged."""
    pm = Mock()
    pm.project_data = {"calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}}}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() == "lateral"


def test_resolve_calibration_perspective_returns_none_when_missing(live_camera_service):
    """Without calibration data the helper returns None (perspective-agnostic
    fallback path inside WeightManager)."""
    pm = Mock()
    pm.project_data = {}
    live_camera_service.project_manager = pm

    assert live_camera_service._resolve_calibration_perspective() is None


def test_resolve_calibration_perspective_returns_none_when_no_project_manager(
    live_camera_service,
):
    """No project loaded → perspective is None and live falls back gracefully."""
    live_camera_service.project_manager = None

    assert live_camera_service._resolve_calibration_perspective() is None


def test_is_session_active_false_when_no_threads(live_camera_service):
    """Fresh service (no threads spawned) is not active."""
    live_camera_service.capture_thread = None
    live_camera_service.processing_thread = None
    live_camera_service.video_recording_thread = None

    assert live_camera_service.is_session_active() is False


def test_is_session_active_true_when_capture_thread_alive(live_camera_service):
    """Active capture thread → session is active."""
    alive_thread = Mock()
    alive_thread.is_alive.return_value = True
    live_camera_service.capture_thread = alive_thread
    live_camera_service.processing_thread = None
    live_camera_service.video_recording_thread = None

    assert live_camera_service.is_session_active() is True


def test_is_session_active_false_when_threads_finished(live_camera_service):
    """Threads exist but already exited → session is not active."""
    dead_thread = Mock()
    dead_thread.is_alive.return_value = False
    live_camera_service.capture_thread = dead_thread
    live_camera_service.processing_thread = dead_thread
    live_camera_service.video_recording_thread = dead_thread

    assert live_camera_service.is_session_active() is False


def test_cleanup_existing_session_folders_no_base(live_camera_service, tmp_path):
    """Return early when output base does not exist."""
    missing_dir = tmp_path / "missing"

    live_camera_service._cleanup_existing_session_folders(missing_dir, "exp1")

    assert not missing_dir.exists()


def test_cleanup_existing_session_folders_removes_matching(live_camera_service, tmp_path):
    """Remove all experiment folders matching pattern."""
    base_dir = tmp_path / "sessions"
    base_dir.mkdir()

    exp1_a = base_dir / "exp1_20240101_010101"
    exp1_b = base_dir / "exp1_20240101_020202"
    exp2 = base_dir / "exp2_20240101_010101"

    exp1_a.mkdir()
    exp1_b.mkdir()
    exp2.mkdir()

    live_camera_service._cleanup_existing_session_folders(base_dir, "exp1")

    assert not exp1_a.exists()
    assert not exp1_b.exists()
    assert exp2.exists()


def test_threadsafe_properties_round_trip(live_camera_service):
    """Verify thread-safe getters/setters."""
    camera = Mock()
    preview = Mock()

    live_camera_service.camera = camera
    live_camera_service.preview_window = preview
    live_camera_service.is_capturing_for_video = True
    live_camera_service.timer_id = "timer-1"

    assert live_camera_service.camera is camera
    assert live_camera_service.preview_window is preview
    assert live_camera_service.is_capturing_for_video is True
    assert live_camera_service.timer_id == "timer-1"


def test_on_disconnect_user_action_sets_state(live_camera_service):
    live_camera_service._camera_disconnected = True

    live_camera_service._on_disconnect_user_action({"action": "resume", "experiment_id": "exp1"})

    assert live_camera_service._user_disconnect_action == "resume"


def test_on_disconnect_user_action_stop_calls_stop_session(live_camera_service):
    live_camera_service.stop_session = Mock()

    live_camera_service._on_disconnect_user_action({"action": "stop", "experiment_id": "exp1"})

    assert live_camera_service._user_disconnect_action == "stop"
    live_camera_service.stop_session.assert_called_once()


def test_adjust_fps_dynamically_increases_skip(live_camera_service):
    live_camera_service._fps_adjustment_interval = 1
    live_camera_service._target_fps = 30.0
    live_camera_service._frame_skip_count = 0
    live_camera_service._processing_times = [0.1] * 9

    should_process = live_camera_service._adjust_fps_dynamically(10, 0.1)

    assert should_process is True
    assert live_camera_service._frame_skip_count == 1


def test_adjust_fps_dynamically_decreases_skip(live_camera_service):
    live_camera_service._fps_adjustment_interval = 1
    live_camera_service._target_fps = 30.0
    live_camera_service._frame_skip_count = 2
    live_camera_service._processing_times = [0.01] * 9

    should_process = live_camera_service._adjust_fps_dynamically(10, 0.01)

    assert should_process is True
    assert live_camera_service._frame_skip_count == 1


def test_adjust_fps_dynamically_skips_frames(live_camera_service):
    live_camera_service._frame_skip_count = 1

    assert live_camera_service._adjust_fps_dynamically(1, 0.05) is False
    assert live_camera_service._adjust_fps_dynamically(2, 0.05) is True


def test_clear_queues_drains_all_items(live_camera_service):
    live_camera_service.frame_queue.put_nowait((1, "frame"))
    live_camera_service.video_queue.put_nowait((1, "video"))

    live_camera_service._clear_queues()

    assert live_camera_service.frame_queue.empty()
    assert live_camera_service.video_queue.empty()


def test_check_camera_disconnect_publishes_and_pauses(live_camera_service, monkeypatch):
    live_camera_service._last_valid_frame_time = 10.0
    live_camera_service._camera_disconnect_threshold_s = 2.0
    live_camera_service._analysis_params = {"experiment_id": "exp-1"}

    live_camera_service.recorder.pause_recording = Mock()

    monkeypatch.setattr(camera_conn_module.time, "time", lambda: 13.0)

    live_camera_service._check_camera_disconnect()

    assert live_camera_service._camera_disconnected is True
    assert live_camera_service._recording_paused is True
    assert live_camera_service._disconnect_gaps[-1] == (10.0, None)
    live_camera_service.recorder.pause_recording.assert_called_once()
    live_camera_service.event_bus.publish.assert_called_once()


def test_check_camera_disconnect_no_last_frame_noop(live_camera_service):
    live_camera_service._last_valid_frame_time = None

    live_camera_service._check_camera_disconnect()

    live_camera_service.event_bus.publish.assert_not_called()


def test_on_camera_reconnected_resumes_and_publishes(live_camera_service, monkeypatch):
    live_camera_service._camera_disconnected = True
    live_camera_service._recording_paused = True
    live_camera_service._disconnect_gaps = [(10.0, None)]
    live_camera_service.recorder.resume_recording = Mock()

    monkeypatch.setattr(camera_conn_module.time, "time", lambda: 15.0)

    live_camera_service._on_camera_reconnected()

    assert live_camera_service._camera_disconnected is False
    assert live_camera_service._recording_paused is False
    assert live_camera_service._disconnect_gaps[-1] == (10.0, 15.0)
    live_camera_service.recorder.resume_recording.assert_called_once()
    live_camera_service.event_bus.publish.assert_called_once()


def test_release_preview_camera_releases_hardware_vm_camera(live_camera_service):
    """At session start the project-level preview Camera (held by hardware_vm)
    must be released, otherwise its physical device stays powered on alongside
    the session camera — which is exactly what users observe with per-session
    overrides (two cameras lit at once)."""
    preview_camera = Mock()
    hardware_vm = Mock()
    hardware_vm.camera = preview_camera
    hardware_vm.active_frame_source = preview_camera
    controller = Mock()
    controller.hardware_vm = hardware_vm
    live_camera_service.controller = controller

    live_camera_service._release_preview_camera_if_any()

    preview_camera.release.assert_called_once()
    assert hardware_vm.camera is None
    assert hardware_vm.active_frame_source is None


def test_release_preview_camera_no_hardware_vm_is_noop(live_camera_service):
    """When there is no controller / hardware_vm (tests, headless), the helper
    must silently no-op — never crash the session start path."""
    live_camera_service.controller = None
    # Must not raise.
    live_camera_service._release_preview_camera_if_any()


def test_release_preview_camera_swallows_release_exception(live_camera_service):
    """A failure inside Camera.release must not abort the session — log and
    proceed (the device will be reclaimed when the process exits anyway)."""
    preview_camera = Mock()
    preview_camera.release.side_effect = RuntimeError("cv2 hiccup")
    hardware_vm = Mock()
    hardware_vm.camera = preview_camera
    hardware_vm.active_frame_source = preview_camera
    controller = Mock()
    controller.hardware_vm = hardware_vm
    live_camera_service.controller = controller

    live_camera_service._release_preview_camera_if_any()

    preview_camera.release.assert_called_once()
    assert hardware_vm.camera is None
