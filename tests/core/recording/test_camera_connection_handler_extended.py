"""
Unit tests for ``camera_connection_handler``: payload helper, camera setup and
warm-up, preview window choice, and the disconnect/reconnect state machine.

The camera is faked at the ``zebtrack.io.camera.Camera`` boundary and the
module clock is replaced by a deterministic one, so no test touches hardware
or waits on the real clock.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from zebtrack.core.recording import camera_connection_handler as handler_module
from zebtrack.core.recording.camera_connection_handler import (
    CameraConnectionMixin,
    _payload_get,
)
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents


@dataclass
class DummyPayload:
    camera_index: int
    name: str


class TestCameraConnectionHandlerExtended:
    """Test helper functions in camera_connection_handler."""

    def test_payload_get_dict(self):
        d = {"camera_index": 2, "name": "usb_cam"}
        assert _payload_get(d, "camera_index") == 2
        assert _payload_get(d, "name") == "usb_cam"
        assert _payload_get(d, "missing", default=99) == 99

    def test_payload_get_dataclass(self):
        payload = DummyPayload(camera_index=1, name="main_cam")
        assert _payload_get(payload, "camera_index") == 1
        assert _payload_get(payload, "name") == "main_cam"
        assert _payload_get(payload, "missing", default="none") == "none"

    def test_payload_get_other_or_none(self):
        assert _payload_get(None, "key", default="fallback") == "fallback"
        assert _payload_get("string_payload", "key", default=42) == 42

    def test_payload_get_dataclass_class_is_not_an_instance(self):
        # A dataclass TYPE passes ``is_dataclass`` too; reading attributes off
        # the class would return field defaults that no event ever carried.
        assert _payload_get(DummyPayload, "camera_index", default="x") == "x"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _CameraCfg(BaseModel):
    index: int = 0
    desired_width: int = 640
    desired_height: int = 480


class _FakeSettings(BaseModel):
    camera: _CameraCfg = _CameraCfg()


class _Clock:
    """Deterministic replacement for the ``time`` module used by the handler."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _FakeCamera:
    """Scripted stand-in for ``zebtrack.io.camera.Camera``."""

    instances: ClassVar[list[_FakeCamera]] = []
    opened = True
    frames: ClassVar[list[bool]] = []
    index_offset = 0
    raise_on_init: Exception | None = None

    def __init__(self, settings_obj):
        if _FakeCamera.raise_on_init is not None:
            raise _FakeCamera.raise_on_init
        self.settings_obj = settings_obj
        self._camera_index = settings_obj.camera.index + _FakeCamera.index_offset
        self.actual_width = settings_obj.camera.desired_width
        self.actual_height = settings_obj.camera.desired_height
        self.reads = 0
        _FakeCamera.instances.append(self)

    def is_opened(self) -> bool:
        return _FakeCamera.opened

    def get_frame(self):
        ok = _FakeCamera.frames[self.reads % len(_FakeCamera.frames)]
        self.reads += 1
        return (True, object()) if ok else (False, None)


class _Host(CameraConnectionMixin):
    """Minimal host carrying only what the mixin reads."""

    # Test doubles stand in for these collaborators.
    controller: Any
    event_bus: Any
    project_manager: Any

    def __init__(self) -> None:
        self.controller = None
        self.settings = _FakeSettings(camera=_CameraCfg(index=0))
        self.recorder = Mock()
        self.event_bus = Mock()
        self.project_manager = Mock()
        self.root = None
        self._lock = threading.Lock()
        self._last_valid_frame_time = None
        self._camera_disconnect_threshold_s = 2.0
        self._camera_disconnected = False
        self._disconnect_gaps = []
        self._recording_paused = False
        self._analysis_params = {}
        self._user_disconnect_action = None
        self.camera = None
        self.preview_window = None
        self.stop_calls = 0

    def stop_session(self, *, cancelled: bool = False, keep_data: bool = False) -> bool:
        self.stop_calls += 1
        return True


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(handler_module, "time", fake)
    return fake


@pytest.fixture
def fake_camera(monkeypatch):
    _FakeCamera.instances = []
    _FakeCamera.opened = True
    _FakeCamera.frames = [True]
    _FakeCamera.index_offset = 0
    _FakeCamera.raise_on_init = None
    import zebtrack.io.camera as camera_module

    monkeypatch.setattr(camera_module, "Camera", _FakeCamera)
    return _FakeCamera


def _published(host: _Host):
    return [c.args[0] for c in host.event_bus.publish.call_args_list]


# ---------------------------------------------------------------------------
# _setup_camera
# ---------------------------------------------------------------------------


class TestSetupCamera:
    def test_opens_requested_index_at_forced_720p_without_touching_settings(
        self, clock, fake_camera
    ):
        host = _Host()

        assert host._setup_camera(3) is True

        cam = fake_camera.instances[0]
        assert host.camera is cam
        assert cam.settings_obj.camera.index == 3
        assert (cam.settings_obj.camera.desired_width, cam.settings_obj.camera.desired_height) == (
            1280,
            720,
        )
        # The session copy is private: the shared settings keep their values.
        assert host.settings.camera.index == 0
        assert host.settings.camera.desired_width == 640

    def test_warmup_reads_fifty_frames_when_every_read_succeeds(self, clock, fake_camera):
        host = _Host()

        host._setup_camera(0)

        cam = fake_camera.instances[0]
        assert cam.reads == 50
        # One 0.05 s pause per successful read, no 0.1 s retry pause.
        assert clock.slept == [0.05] * 50

    def test_failed_reads_add_a_retry_pause(self, clock, fake_camera):
        fake_camera.frames = [False]
        host = _Host()

        # 50 failures x 0.15 s = 7.5 s > 5 s timeout: stops early, still True
        # (a poor warm-up is a warning, not a refusal).
        assert host._setup_camera(0) is True

        cam = fake_camera.instances[0]
        # Each failed read costs 0.1 + 0.05 s; the loop stops once >5 s passed.
        # After n reads elapsed = 0.15 n; the check before read n+1 needs
        # 0.15 n > 5 -> n = 34.
        assert cam.reads == 34
        assert clock.slept[:2] == [0.1, 0.05]

    def test_camera_not_opened_returns_false(self, clock, fake_camera):
        fake_camera.opened = False
        host = _Host()

        assert host._setup_camera(1) is False
        assert fake_camera.instances[0].reads == 0

    def test_index_mismatch_is_refused(self, clock, fake_camera):
        # The driver fell back to another device: recording from it would
        # film the wrong arena.
        fake_camera.index_offset = 1
        host = _Host()

        assert host._setup_camera(2) is False

    def test_constructor_failure_returns_false(self, clock, fake_camera):
        fake_camera.raise_on_init = OSError("Cannot open camera at index 5")
        host = _Host()

        assert host._setup_camera(5) is False
        assert host.camera is None

    def test_parked_preview_camera_is_released_before_opening(self, clock, fake_camera):
        host = _Host()
        preview = Mock()
        other_source = Mock()
        host.controller = SimpleNamespace(
            hardware_vm=SimpleNamespace(camera=preview, active_frame_source=other_source)
        )

        host._setup_camera(0)

        preview.release.assert_called_once_with()
        assert host.controller.hardware_vm.camera is None
        # A different active source is not the preview camera: left alone.
        assert host.controller.hardware_vm.active_frame_source is other_source


# ---------------------------------------------------------------------------
# _create_preview_window
# ---------------------------------------------------------------------------


class TestCreatePreviewWindow:
    @pytest.fixture
    def windows(self, monkeypatch):
        import zebtrack.ui.dialogs as dialogs
        import zebtrack.ui.dialogs.multi_aquarium_live_preview_window as multi_mod

        single = Mock(name="LivePreviewWindow")
        multi = Mock(name="MultiAquariumLivePreviewWindow")
        monkeypatch.setattr(dialogs, "LivePreviewWindow", single)
        monkeypatch.setattr(multi_mod, "MultiAquariumLivePreviewWindow", multi)
        return single, multi

    def test_single_zone_builds_single_preview(self, windows):
        from zebtrack.core.detection import ZoneData

        single, multi = windows
        host = _Host()
        host.project_manager.get_zone_data.return_value = ZoneData()

        host._create_preview_window(4, 60.0)

        multi.assert_not_called()
        kwargs = single.call_args.kwargs
        assert kwargs["camera_index"] == 4
        assert kwargs["duration_s"] == 60.0
        assert host.preview_window is single.return_value
        # The window's stop button stops the session.
        kwargs["on_stop_callback"]()
        assert host.stop_calls == 1

    def test_multi_aquarium_zone_builds_multi_preview_with_count(self, windows):
        from zebtrack.core.project.zone_manager import MultiAquariumZoneData

        single, multi = windows
        zone = MultiAquariumZoneData()
        zone.aquariums = [Mock(), Mock(), Mock()]
        host = _Host()
        host.project_manager.get_zone_data.return_value = zone

        host._create_preview_window(1, 30.0)

        single.assert_not_called()
        assert multi.call_args.kwargs["num_aquariums"] == 3
        assert host.preview_window is multi.return_value

    def test_without_project_manager_uses_single_preview(self, windows):
        single, multi = windows
        host = _Host()
        host.project_manager = None

        host._create_preview_window(0, 10.0)

        single.assert_called_once()
        multi.assert_not_called()


# ---------------------------------------------------------------------------
# Disconnect / reconnect
# ---------------------------------------------------------------------------


class TestCheckCameraDisconnect:
    def test_gap_below_threshold_is_not_a_disconnect(self, clock):
        host = _Host()
        host._last_valid_frame_time = clock.now - 1.5

        host._check_camera_disconnect()

        assert host._camera_disconnected is False
        assert host._disconnect_gaps == []
        host.recorder.pause_recording.assert_not_called()
        host.event_bus.publish.assert_not_called()

    def test_gap_exactly_at_threshold_is_not_a_disconnect(self, clock):
        host = _Host()
        host._last_valid_frame_time = clock.now - 2.0

        host._check_camera_disconnect()

        assert host._camera_disconnected is False

    def test_disconnect_payload_carries_gap_and_experiment(self, clock):
        host = _Host()
        host._analysis_params = {"experiment_id": "CECT_4"}
        start = clock.now - 3.5
        host._last_valid_frame_time = start

        host._check_camera_disconnect()

        (event,) = _published(host)
        assert event.type == UIEvents.CAMERA_DISCONNECT_DETECTED
        assert event.data == payloads.CameraDisconnectPayload(
            gap_duration_s=3.5, gap_start_time=start, experiment_id="CECT_4"
        )
        assert host._disconnect_gaps == [(start, None)]
        assert host._recording_paused is True
        host.recorder.pause_recording.assert_called_once_with()

    def test_experiment_defaults_to_unknown(self, clock):
        host = _Host()
        host._last_valid_frame_time = clock.now - 10

        host._check_camera_disconnect()

        assert _published(host)[0].data.experiment_id == "unknown"

    def test_second_check_while_disconnected_adds_nothing(self, clock):
        host = _Host()
        host._last_valid_frame_time = clock.now - 3

        host._check_camera_disconnect()
        clock.now += 5
        host._check_camera_disconnect()

        assert len(host._disconnect_gaps) == 1
        assert host.event_bus.publish.call_count == 1
        host.recorder.pause_recording.assert_called_once()

    def test_already_paused_recorder_is_not_paused_again(self, clock):
        host = _Host()
        host._recording_paused = True
        host._last_valid_frame_time = clock.now - 3

        host._check_camera_disconnect()

        host.recorder.pause_recording.assert_not_called()

    @pytest.mark.parametrize("error", [AttributeError("no pause"), OSError("disk")])
    def test_pause_failure_still_publishes_and_records_gap(self, clock, error):
        host = _Host()
        host.recorder.pause_recording.side_effect = error
        host._last_valid_frame_time = clock.now - 3

        host._check_camera_disconnect()

        assert host._recording_paused is False
        assert host._camera_disconnected is True
        assert len(host._disconnect_gaps) == 1
        assert host.event_bus.publish.call_count == 1

    def test_no_recorder_and_no_bus_still_records_gap(self, clock):
        host = _Host()
        host.recorder = None
        host.event_bus = None
        host._last_valid_frame_time = clock.now - 3

        host._check_camera_disconnect()

        assert host._camera_disconnected is True
        assert len(host._disconnect_gaps) == 1


class TestOnCameraReconnected:
    def test_not_disconnected_is_a_noop(self, clock):
        host = _Host()

        host._on_camera_reconnected()

        host.recorder.resume_recording.assert_not_called()
        host.event_bus.publish.assert_not_called()

    def test_closes_open_gap_and_reports_total(self, clock):
        host = _Host()
        host._camera_disconnected = True
        host._recording_paused = True
        host._disconnect_gaps = [(100.0, 104.0), (clock.now - 7.0, None)]

        host._on_camera_reconnected()

        assert host._disconnect_gaps[-1] == (clock.now - 7.0, clock.now)
        (event,) = _published(host)
        assert event.type == UIEvents.CAMERA_RECONNECTED
        assert event.data.gap_duration_s == pytest.approx(7.0)
        assert event.data.total_gaps == 2
        assert host._camera_disconnected is False

    def test_closed_last_gap_is_not_rewritten(self, clock):
        host = _Host()
        host._camera_disconnected = True
        host._disconnect_gaps = [(10.0, 12.0)]

        host._on_camera_reconnected()

        assert host._disconnect_gaps == [(10.0, 12.0)]
        assert _published(host)[0].data.gap_duration_s == 0.0

    def test_without_gaps_reports_zero(self, clock):
        host = _Host()
        host._camera_disconnected = True

        host._on_camera_reconnected()

        data = _published(host)[0].data
        assert data.gap_duration_s == 0.0
        assert data.total_gaps == 0

    def test_unpaused_recorder_is_not_resumed(self, clock):
        host = _Host()
        host._camera_disconnected = True
        host._recording_paused = False

        host._on_camera_reconnected()

        host.recorder.resume_recording.assert_not_called()

    @pytest.mark.parametrize("error", [AttributeError("no resume"), OSError("disk")])
    def test_resume_failure_keeps_paused_flag(self, clock, error):
        host = _Host()
        host._camera_disconnected = True
        host._recording_paused = True
        host.recorder.resume_recording.side_effect = error

        host._on_camera_reconnected()

        assert host._recording_paused is True
        assert host._camera_disconnected is False
        assert host.event_bus.publish.call_count == 1


class TestDisconnectUserAction:
    def test_wait_records_action_and_does_not_stop(self):
        host = _Host()

        host._on_disconnect_user_action(payloads.CameraDisconnectPayload(action="wait"))

        assert host._user_disconnect_action == "wait"
        assert host.stop_calls == 0

    def test_resume_records_action_without_stopping(self):
        host = _Host()
        host._camera_disconnected = True

        host._on_disconnect_user_action({"action": "resume"})

        assert host._user_disconnect_action == "resume"
        assert host.stop_calls == 0

    def test_stop_from_dataclass_payload_stops_session(self):
        host = _Host()

        host._on_disconnect_user_action(
            payloads.CameraDisconnectPayload(action="stop", experiment_id="e1")
        )

        assert host._user_disconnect_action == "stop"
        assert host.stop_calls == 1

    def test_missing_action_defaults_to_wait(self):
        host = _Host()

        host._on_disconnect_user_action({})

        assert host._user_disconnect_action == "wait"
        assert host.stop_calls == 0
