"""
Extended unit tests for LiveSessionManagerMixin in core/recording/live_session_manager.py.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.recording import live_session_manager as lsm_module
from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin
from zebtrack.settings import load_settings
from zebtrack.ui.event_bus_v2 import UIEvents


class DummyLiveService(LiveSessionManagerMixin):
    def __init__(self, tmp_path: Path):
        self.settings = load_settings()
        self.project_manager = MagicMock()
        self.project_workflow_service = MagicMock()
        self.state_manager = MagicMock()
        self.detector_service = MagicMock()
        self.recording_service = MagicMock()
        self.event_bus: Any = MagicMock()
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None
        self._analysis_params = {}


class TestLiveSessionManagerExtended:
    def test_cleanup_existing_session_folders(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        output_base = tmp_path / "sessions"
        output_base.mkdir(parents=True, exist_ok=True)

        # Matching folders
        match1 = output_base / "exp123_20260816_100000"
        match1.mkdir()
        match2 = output_base / "exp123_20260816_110000"
        match2.mkdir()
        # Non-matching folder
        other = output_base / "other_exp_20260816_120000"
        other.mkdir()

        service._cleanup_existing_session_folders(output_base, "exp123")
        assert not match1.exists()
        assert not match2.exists()
        assert other.exists()

    def test_cleanup_non_existent_folder_noop(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        service._cleanup_existing_session_folders(tmp_path / "non_existent", "exp123")

    def test_cleanup_preserves_folders_holding_a_recording(self, tmp_path: Path):
        """Gravar de novo com o mesmo id NAO pode apagar a sessao anterior."""
        service = DummyLiveService(tmp_path)
        output_base = tmp_path / "sessions"
        output_base.mkdir()

        with_video = output_base / "exp123_20260816_100000"
        with_video.mkdir()
        (with_video / "exp123_20260816_100000.mp4").write_bytes(b"video")

        with_trajectory = output_base / "exp123_20260816_110000"
        with_trajectory.mkdir()
        (with_trajectory / "3_CoordMovimento_exp123.parquet").write_bytes(b"parquet")

        leftover = output_base / "exp123_20260816_120000"
        leftover.mkdir()

        service._cleanup_existing_session_folders(output_base, "exp123")

        assert with_video.exists()
        assert with_trajectory.exists()
        assert not leftover.exists()

    def test_cleanup_removes_cancelled_folder_even_with_video(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        output_base = tmp_path / "sessions"
        output_base.mkdir()

        cancelled = output_base / "exp123_20260816_100000"
        cancelled.mkdir()
        (cancelled / "exp123_20260816_100000.mp4").write_bytes(b"partial")
        (cancelled / ".cancelled").write_text("forced=True", encoding="utf-8")

        service._cleanup_existing_session_folders(output_base, "exp123")

        assert not cancelled.exists()

    def test_cleanup_does_not_match_by_prefix(self, tmp_path: Path):
        """``CTRL`` nao pode varrer as pastas de ``CTRL_1`` (glob por prefixo)."""
        service = DummyLiveService(tmp_path)
        output_base = tmp_path / "sessions"
        output_base.mkdir()

        other_experiment = output_base / "CTRL_1_20260816_100000"
        other_experiment.mkdir()
        own_leftover = output_base / "CTRL_20260816_100000"
        own_leftover.mkdir()

        service._cleanup_existing_session_folders(output_base, "CTRL")

        assert other_experiment.exists()
        assert not own_leftover.exists()

    def test_cleanup_ignores_folders_not_named_like_a_session(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        output_base = tmp_path / "sessions"
        output_base.mkdir()

        manual_folder = output_base / "exp123_backup"
        manual_folder.mkdir()

        service._cleanup_existing_session_folders(output_base, "exp123")

        assert manual_folder.exists()

    def test_startup_status_publishes_and_repaints(self, tmp_path: Path):
        """Start bloqueia a thread do Tk por segundos; sem repaint a janela "morre"."""
        service = DummyLiveService(tmp_path)
        service.root = MagicMock()
        service.preview_window = None

        service._publish_startup_status("carregando detector")

        service.event_bus.publish.assert_called_once()
        event = service.event_bus.publish.call_args[0][0]
        assert event.data.message == "carregando detector"
        # ``update_idletasks`` e nao ``update``: repinta sem processar cliques,
        # que poderiam reentrar no proprio start.
        service.root.update_idletasks.assert_called_once()
        service.root.update.assert_not_called()

    def test_startup_status_also_feeds_the_preview_window(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        service.root = None
        service.preview_window = MagicMock()

        service._publish_startup_status("abrindo camera")

        service.preview_window.update_status_text.assert_called_once()

    def test_startup_status_survives_a_broken_bus(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        service.root = None
        service.preview_window = None
        service.event_bus.publish.side_effect = RuntimeError("bus down")

        service._publish_startup_status("abrindo camera")  # nao pode abortar o start

    def test_is_session_active(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        assert service.is_session_active() is False

        mock_alive_thread = MagicMock()
        mock_alive_thread.is_alive.return_value = True
        service.processing_thread = mock_alive_thread
        assert service.is_session_active() is True

        mock_dead_thread = MagicMock()
        mock_dead_thread.is_alive.return_value = False
        service.processing_thread = mock_dead_thread
        assert service.is_session_active() is False

    def test_resolve_session_detector_config_project_workflow(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        service.project_manager.project_path = "/path/to/project"
        mock_pw = MagicMock()
        mock_pw.resolve_project_model_settings.return_value = (
            "custom_yolo.pt",
            True,
        )
        service.project_workflow_service = mock_pw

        weight, ov, source = service._resolve_session_detector_config()
        assert weight == "custom_yolo.pt"
        assert ov is True
        assert source == "project_workflow_service"

    def test_resolve_session_detector_config_fallback_settings(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        service.project_manager.project_path = None
        service.settings.model_selection.use_openvino = False

        weight, ov, source = service._resolve_session_detector_config()
        assert weight is None
        assert ov is False
        assert source == "settings"

    def test_resolve_calibration_perspective(self, tmp_path: Path):
        service = DummyLiveService(tmp_path)
        # From project calibration
        service.project_manager.project_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "dorsal"}}
        }
        assert service._resolve_calibration_perspective() == "dorsal"

        # Fallback to analysis_params
        service.project_manager.project_data = {}
        service._analysis_params = {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
        assert service._resolve_calibration_perspective() == "lateral"

        # None when missing
        service._analysis_params = {}
        assert service._resolve_calibration_perspective() is None


class TestLiveSessionManagerExtended2:
    def test_resolve_session_detector_config_with_project(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mock_pws = MagicMock()
        mock_pws.resolve_project_model_settings.return_value = ("custom_weights.pt", True)
        mock_pm = MagicMock()
        mock_pm.project_path = "/path/to/project"

        mixin.project_workflow_service = mock_pws
        mixin.project_manager = mock_pm

        weight, openvino, source = mixin._resolve_session_detector_config()
        assert weight == "custom_weights.pt"
        assert openvino is True
        assert source == "project_workflow_service"

    def test_resolve_session_detector_config_fallback_settings(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.project_workflow_service = None
        mixin.project_manager = None  # type: ignore[assignment]
        mixin.settings = MagicMock()
        mixin.settings.model_selection.use_openvino = False

        weight, openvino, source = mixin._resolve_session_detector_config()
        assert weight is None
        assert openvino is False
        assert source == "settings"

    def test_resolve_calibration_perspective_from_project(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.project_manager = MagicMock()
        mixin.project_manager.project_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "top_down"}}
        }
        mixin._analysis_params = {}

        assert mixin._resolve_calibration_perspective() == "top_down"

    def test_resolve_calibration_perspective_from_analysis_params(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.project_manager = None  # type: ignore[assignment]
        mixin._analysis_params = {"behavioral_analysis": {"aquarium_perspective": "lateral"}}

        assert mixin._resolve_calibration_perspective() == "lateral"

    def test_is_session_active_all_dead(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.capture_thread = None
        mixin.processing_thread = None
        mixin.video_recording_thread = None

        assert mixin.is_session_active() is False

    def test_is_session_active_any_alive(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True

        mixin.capture_thread = mock_thread
        mixin.processing_thread = None
        mixin.video_recording_thread = None

        assert mixin.is_session_active() is True

    def test_cleanup_existing_session_folders_empty_or_missing(self, tmp_path: Path):
        mixin = object.__new__(LiveSessionManagerMixin)
        non_existent = tmp_path / "does_not_exist"

        # Should return safely without raising
        mixin._cleanup_existing_session_folders(non_existent, "exp_1")

        # When directory exists with no matches
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        mixin._cleanup_existing_session_folders(output_dir, "exp_1")
        assert output_dir.exists()

    def test_detect_and_mark_cancellation_force(self, tmp_path: Path):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.recorder = MagicMock()
        mixin.recorder.start_time = 100.0
        mixin.current_output_dir = tmp_path
        mixin._session_duration_s = 60.0

        res = mixin._detect_and_mark_cancellation(force=True)
        assert res is True
        marker = tmp_path / ".cancelled"
        assert marker.exists()
        content = marker.read_text(encoding="utf-8")
        assert "forced=True" in content

    def test_detect_and_mark_cancellation_no_recorder(self):
        mixin = object.__new__(LiveSessionManagerMixin)
        mixin.recorder = None
        mixin.current_output_dir = None
        mixin._session_duration_s = 0.0

        assert mixin._detect_and_mark_cancellation(force=False) is False


class DummyLiveServicePart3(LiveSessionManagerMixin):
    def __init__(self):
        self.project_workflow_service: Any = None
        self.project_manager: Any = None
        self.settings = MagicMock()
        self._analysis_params: dict = {}
        self.capture_thread: Any = None
        self.processing_thread: Any = None
        self.video_recording_thread: Any = None


class TestLiveSessionManagerExtended3:
    def test_resolve_session_detector_config_with_project(self):
        svc = DummyLiveServicePart3()
        svc.project_manager = MagicMock()
        svc.project_manager.project_path = "/path/project"
        svc.project_workflow_service = MagicMock()
        svc.project_workflow_service.resolve_project_model_settings.return_value = (
            "custom.pt",
            True,
        )

        weight, openvino, source = svc._resolve_session_detector_config()
        assert weight == "custom.pt"
        assert openvino is True
        assert source == "project_workflow_service"

    def test_resolve_calibration_perspective_from_project(self):
        svc = DummyLiveServicePart3()
        svc.project_manager = MagicMock()
        svc.project_manager.project_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
        }

        assert svc._resolve_calibration_perspective() == "lateral"

    def test_resolve_calibration_perspective_from_analysis_params(self):
        svc = DummyLiveServicePart3()
        svc.project_manager = None
        svc._analysis_params = {"behavioral_analysis": {"aquarium_perspective": "top_down"}}

        assert svc._resolve_calibration_perspective() == "top_down"

    def test_is_session_active_lifecycle(self):
        svc = DummyLiveServicePart3()
        assert svc.is_session_active() is False

        mock_t = MagicMock(spec=threading.Thread)
        mock_t.is_alive.return_value = True
        svc.processing_thread = mock_t

        assert svc.is_session_active() is True

    def test_cleanup_existing_session_folders_missing_base(self, tmp_path: Path):
        svc = DummyLiveServicePart3()
        non_existent = tmp_path / "does_not_exist"
        # Should return safely without raising
        svc._cleanup_existing_session_folders(non_existent, "exp_1")

    def test_cleanup_existing_session_folders_matching_dirs(self, tmp_path: Path):
        svc = DummyLiveServicePart3()
        base_dir = tmp_path / "sessions"
        base_dir.mkdir()

        match1 = base_dir / "exp1_20260817_120000"
        match1.mkdir()
        match2 = base_dir / "exp1_20260817_130000"
        match2.mkdir()
        other = base_dir / "exp2_20260817_140000"
        other.mkdir()

        svc._cleanup_existing_session_folders(base_dir, "exp1")

        assert not match1.exists()
        assert not match2.exists()
        assert other.exists()


class DummyLiveServicePart4(LiveSessionManagerMixin):
    def __init__(self):
        self.project_workflow_service: Any = None
        self.project_manager: Any = None
        self.settings = MagicMock()
        self._analysis_params: dict = {}
        self._arena_defined_event = threading.Event()
        self.current_output_dir: Path | None = None
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None


class TestLiveSessionManagerExtended4:
    def test_resolve_session_detector_config_settings_fallback(self):
        svc = DummyLiveServicePart4()
        svc.project_manager = None
        svc.settings.model_selection.use_openvino = True

        weight, openvino, source = svc._resolve_session_detector_config()
        assert weight is None
        assert openvino is True
        assert source == "settings"

    def test_arena_defined_event_initial(self):
        svc = DummyLiveServicePart4()
        assert svc._arena_defined_event.is_set() is False
        svc._arena_defined_event.set()
        assert svc._arena_defined_event.is_set() is True

    def test_resolve_calibration_perspective(self):
        svc = DummyLiveServicePart4()
        svc.project_manager = MagicMock()
        svc.project_manager.project_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "top_down"}}
        }
        assert svc._resolve_calibration_perspective() == "top_down"

        # Fallback to analysis params
        svc.project_manager = None
        svc._analysis_params = {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
        assert svc._resolve_calibration_perspective() == "lateral"

    def test_is_session_active_lifecycle(self):
        svc = DummyLiveServicePart4()
        assert svc.is_session_active() is False

        mock_th = MagicMock(spec=threading.Thread)
        mock_th.is_alive.return_value = True
        svc.capture_thread = mock_th
        assert svc.is_session_active() is True


class DummyLiveService5(LiveSessionManagerMixin):
    def __init__(self):
        self.exit_event = threading.Event()
        self.exit_event.set()
        self.controller = MagicMock()
        self.controller._disable_live_preview_window = True


class TestLiveSessionManagerExtended5:
    def test_start_session_resets_exit_event_and_counters(self):
        svc = DummyLiveService5()
        assert svc.exit_event.is_set() is True

        svc.exit_event.clear()
        assert svc.exit_event.is_set() is False

    def test_live_session_parameters_stored(self):
        svc = DummyLiveService5()
        svc._animals_per_aquarium = 1
        svc._experiment_id = "Session_001"
        svc.analysis_completed = False
        svc._dropped_frames_processing = 0
        svc._dropped_frames_video = 0

        assert svc._animals_per_aquarium == 1
        assert svc._experiment_id == "Session_001"
        assert svc.analysis_completed is False
        assert svc._dropped_frames_processing == 0
        assert svc._dropped_frames_video == 0


class _IntervalProbeService(LiveSessionManagerMixin):
    """Enough of LiveCameraService to reach the detector preparation in start_session."""

    def __init__(self, detector: Any):
        self.settings = MagicMock()
        self.settings.model_selection.animal_method = "det"
        self.project_manager = MagicMock()
        self.project_manager.project_path = None
        self.project_manager.project_data = {}
        self.project_manager.get_zone_data.return_value = MagicMock(polygon=[[0, 0], [1, 1]])
        self.project_workflow_service = None
        self.state_manager = MagicMock()
        self.state_manager.get_detector_state.return_value = MagicMock(
            use_openvino=False, active_weight_name=""
        )
        self.detector_service = MagicMock()
        self.detector_service.detector = detector

        def _initialize_detector(**_kwargs: Any) -> tuple[bool, Any]:
            # Like the real service: a (re)built detector is what it then holds.
            self.detector_service.detector = detector
            return True, detector

        self.detector_service.initialize_detector.side_effect = _initialize_detector
        self.recording_service = MagicMock()
        self.recorder = MagicMock()
        self.event_bus: Any = None
        self.root = None
        self.controller = None
        self.exit_event = MagicMock()
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None
        self._analysis_params = {}
        self._saved_detector_context = None
        self._arena_defined_event = MagicMock()
        self._animals_per_aquarium = 1
        self._aquarium_detection_phase = False
        self.camera = MagicMock(actual_fps=30.0, actual_width=640, actual_height=480)
        self.preview_window = None

    def _setup_camera(self, camera_index: int) -> bool:
        return True

    def _start_threads(self) -> bool:
        return False

    def _resolve_session_multi_zone_data(self) -> Any:
        return None

    def set_last_detections(self, detections: list) -> None:
        pass


class TestSessionIntervalReachesTheDetector:
    """#667: the live detector's Kalman dt is the session's detection cadence.

    Both live paths (project grid and ad-hoc dialog) start through here, so the
    session's ``analysis_interval_frames`` is declared to the detector once,
    beside the camera's real frame rate.
    """

    def test_session_interval_is_declared_to_the_detector(self, tmp_path):
        detector = MagicMock()
        svc = _IntervalProbeService(detector)

        svc.start_session(
            camera_index=0,
            duration_s=10.0,
            experiment_id="day1_G1_S1",
            analysis_interval_frames=7,
            record_video=False,
            output_base_dir=tmp_path,
            zones_validated=True,
        )

        detector.set_processing_interval.assert_called_once_with(7)

    def test_a_real_detector_builds_its_tracker_with_the_session_interval(self, tmp_path):
        from zebtrack.core.detection import SingleDetector
        from zebtrack.plugins.base import DetectorPlugin

        settings_obj = load_settings()
        settings_obj.video_processing.processing_interval = 10
        settings_obj.tracking.use_bytetrack = True
        plugin = MagicMock(spec=DetectorPlugin)
        plugin.get_name.return_value = "MockDetector"
        plugin.detect.return_value = []
        detector = SingleDetector(plugin=plugin, settings_obj=settings_obj)
        svc = _IntervalProbeService(detector)

        svc.start_session(
            camera_index=0,
            duration_s=10.0,
            experiment_id="day1_G1_S1",
            analysis_interval_frames=3,
            record_video=False,
            output_base_dir=tmp_path,
            zones_validated=True,
        )
        tracker = detector._ensure_byte_tracker()

        assert tracker is not None
        assert tracker.processing_interval == 3


class _Recorder:
    """Records how it was stopped; raises when told to."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def stop_recording(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


class TestFinalizeRecorder:
    """A failed save at the end of a live session must reach the operator (audit A5-S-002)."""

    @staticmethod
    def _service(tmp_path: Path, recorder: _Recorder | None) -> DummyLiveService:
        service = DummyLiveService(tmp_path)
        service.recorder = recorder  # type: ignore[assignment]
        service.current_output_dir = tmp_path / "live_20261114_120000"
        return service

    @staticmethod
    def _shown_errors(service: DummyLiveService) -> list[Any]:
        from zebtrack.ui.event_bus_v2 import UIEvents

        events = [call.args[0] for call in service.event_bus.publish.call_args_list]
        return [event for event in events if event.type is UIEvents.SHOW_ERROR]

    def test_a_normal_end_stops_without_forcing_and_reports_nothing(self, tmp_path: Path):
        recorder = _Recorder()
        service = self._service(tmp_path, recorder)

        service._finalize_recorder(cancelled_session=False, threads_hung=False)

        assert recorder.calls == [{}]
        assert service._recorder_stop_error is None
        assert self._shown_errors(service) == []

    def test_a_failed_save_is_shown_with_the_cause_and_the_folder(self, tmp_path: Path):
        service = self._service(tmp_path, _Recorder(OSError("disk full")))

        service._finalize_recorder(cancelled_session=False, threads_hung=False)

        assert service._recorder_stop_error == "disk full"
        (event,) = self._shown_errors(service)
        assert event.data.title == "Recording not saved"
        assert "disk full" in event.data.message
        assert str(service.current_output_dir) in event.data.message
        assert "_BACKUP.json" in event.data.message

    def test_a_failed_save_does_not_abort_the_shutdown(self, tmp_path: Path):
        # Camera, preview and buttons are released after this call: it must return.
        service = self._service(tmp_path, _Recorder(RuntimeError("writer lost")))
        service.event_bus = None

        service._finalize_recorder(cancelled_session=False, threads_hung=False)

        assert service._recorder_stop_error == "writer lost"

    def test_a_cancelled_session_is_forced_and_its_failure_is_not_an_error(self, tmp_path: Path):
        recorder = _Recorder(OSError("already closed"))
        service = self._service(tmp_path, recorder)

        service._finalize_recorder(cancelled_session=True, threads_hung=False)

        assert recorder.calls == [{"force_stop": True, "reason": "user_cancelled"}]
        # The data is being discarded on purpose: nothing was lost that the user wanted.
        assert service._recorder_stop_error is None
        assert self._shown_errors(service) == []

    def test_a_hung_thread_is_recorded_as_the_reason(self, tmp_path: Path):
        recorder = _Recorder()
        service = self._service(tmp_path, recorder)

        service._finalize_recorder(cancelled_session=False, threads_hung=True)

        assert recorder.calls == [{"force_stop": True, "reason": "thread_hang"}]

    def test_an_earlier_failure_does_not_leak_into_the_next_session(self, tmp_path: Path):
        service = self._service(tmp_path, _Recorder(OSError("disk full")))
        service._finalize_recorder(cancelled_session=False, threads_hung=False)

        service.recorder = _Recorder()  # type: ignore[assignment]
        service._finalize_recorder(cancelled_session=False, threads_hung=False)

        assert service._recorder_stop_error is None

    def test_without_a_recorder_there_is_nothing_to_do(self, tmp_path: Path):
        service = self._service(tmp_path, None)
        service._finalize_recorder(cancelled_session=False, threads_hung=False)
        assert service._recorder_stop_error is None


# ---------------------------------------------------------------------------
# start_session / stop_session through the real LiveCameraService facade.
# Hardware (camera, threads, recorder) is faked at the boundary; everything
# the session manager decides on its own runs for real.
# ---------------------------------------------------------------------------

_SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]


class _Harness:
    """A real LiveCameraService with its hardware boundary replaced."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, polygon=True):
        from zebtrack.core.recording.live_camera_service import LiveCameraService

        self.tmp_path = tmp_path
        self.detector = MagicMock(name="detector")
        self.detector._context = "calibration"
        self.svc: Any = LiveCameraService(
            controller=None,
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            recording_service=MagicMock(),
            detector_service=MagicMock(),
            settings_obj=SimpleNamespace(
                model_selection=SimpleNamespace(animal_method="det", use_openvino=False)
            ),
            recorder=MagicMock(),
            event_bus=MagicMock(),
            root=None,
        )
        svc: Any = self.svc
        svc.detector_service.detector = self.detector
        svc.project_manager.project_path = None
        svc.project_manager.project_data = {}
        self.zone = ZoneData(polygon=_SQUARE) if polygon else ZoneData()
        svc.project_manager.get_zone_data.return_value = self.zone
        svc.state_manager.get_detector_state.return_value = SimpleNamespace(
            use_openvino=False, active_weight_name=""
        )
        self.camera = MagicMock(actual_fps=25.0, actual_width=640, actual_height=480)
        self.camera_ok = True
        self.threads_ok = True
        self.recorder_result: bool | Exception = True
        self.recorder_calls: list[tuple[Any, str]] = []
        self.preview_calls: list[tuple[int, float]] = []
        self.stop_calls: list[dict[str, Any]] = []

        def _setup_camera(_index: int) -> bool:
            if self.camera_ok:
                svc.camera = self.camera
            return self.camera_ok

        def _start_live_recorder(zone_data: Any, base_name: str) -> bool:
            self.recorder_calls.append((zone_data, base_name))
            if isinstance(self.recorder_result, Exception):
                raise self.recorder_result
            return self.recorder_result

        def _stop_session(**kwargs: Any) -> bool:
            self.stop_calls.append(kwargs)
            return True

        monkeypatch.setattr(svc, "_setup_camera", _setup_camera)
        monkeypatch.setattr(svc, "_start_threads", lambda: self.threads_ok)
        monkeypatch.setattr(svc, "_start_live_recorder", _start_live_recorder)
        monkeypatch.setattr(svc, "_resolve_session_multi_zone_data", lambda: None)
        monkeypatch.setattr(svc, "_configure_mask_capture", lambda: False)
        monkeypatch.setattr(
            svc,
            "_create_preview_window",
            lambda index, duration: self.preview_calls.append((index, duration)),
        )
        self._stop_session = _stop_session

    def intercept_stop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(self.svc, "stop_session", self._stop_session)

    def start(self, **overrides: Any) -> bool:
        kwargs: dict[str, Any] = {
            "camera_index": 0,
            "duration_s": 30.0,
            "experiment_id": "CECT_4",
            "output_base_dir": self.tmp_path,
            "zones_validated": True,
        }
        kwargs.update(overrides)
        return self.svc.start_session(**kwargs)

    def statuses(self) -> list[str]:
        return [
            c.args[0].data.message
            for c in self.svc.event_bus.publish.call_args_list
            if c.args[0].type == UIEvents.UI_SET_STATUS
        ]


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    return _Harness(tmp_path, monkeypatch)


class TestStartSessionRecordingStart:
    def test_recorder_starts_with_project_zones_and_folder_name(self, harness):
        assert harness.start(session_folder_name="live_20261115_100000") is True

        ((zone, base_name),) = harness.recorder_calls
        assert zone is harness.zone
        assert base_name == "live_20261115_100000"
        assert harness.svc.current_output_dir == harness.tmp_path / "live_20261115_100000"
        assert harness.svc.current_output_dir.is_dir()
        assert harness.svc._session_duration_s == 30.0
        harness.svc.state_manager.update_processing_state.assert_called_once_with(
            source="live_camera_service.start", is_processing=True
        )

    def test_camera_properties_are_kept_for_post_analysis(self, harness):
        harness.start()

        assert harness.svc._actual_fps == 25.0
        assert (harness.svc._actual_width, harness.svc._actual_height) == (640, 480)
        # ByteTrack's buffer follows the camera's real rate (#630).
        harness.detector.set_source_fps.assert_called_once_with(25.0)

    def test_legacy_folder_is_experiment_plus_timestamp(self, harness):
        harness.start()

        name = harness.svc.current_output_dir.name
        assert name.startswith("CECT_4_")
        assert len(name) == len("CECT_4_") + len("YYYYMMDD_HHMMSS")
        assert harness.recorder_calls[0][1] == name

    def test_without_output_dir_uses_the_default_live_folder(self, harness, monkeypatch):
        default = harness.tmp_path / "home_live"
        monkeypatch.setattr(lsm_module, "default_live_sessions_dir", lambda: default)

        harness.start(output_base_dir=None, session_folder_name="s1")

        assert harness.svc.current_output_dir == default / "s1"

    def test_recorder_refusal_stops_the_session(self, harness, monkeypatch):
        harness.intercept_stop(monkeypatch)
        harness.recorder_result = False

        assert harness.start() is False
        assert harness.stop_calls == [{}]

    def test_recorder_exception_stops_the_session(self, harness, monkeypatch):
        harness.intercept_stop(monkeypatch)
        harness.recorder_result = OSError("codec")

        assert harness.start() is False
        assert harness.stop_calls == [{}]

    def test_record_video_false_never_opens_the_recorder(self, harness):
        assert harness.start(record_video=False) is True
        assert harness.recorder_calls == []

    def test_thread_start_failure_aborts_before_recording(self, harness):
        harness.threads_ok = False

        assert harness.start() is False
        assert harness.recorder_calls == []
        harness.svc.state_manager.update_processing_state.assert_not_called()

    def test_camera_failure_aborts_without_a_folder(self, harness):
        harness.camera_ok = False

        assert harness.start(session_folder_name="never") is False
        assert not (harness.tmp_path / "never").exists()

    def test_camera_failure_outside_pytest_shows_the_error(self, harness, monkeypatch):
        import tkinter.messagebox as messagebox

        shown: list[tuple[str, str]] = []
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr(messagebox, "showerror", lambda t, m: shown.append((t, m)))
        harness.camera_ok = False

        assert harness.start(camera_index=7) is False
        ((title, message),) = shown
        assert title == "Camera Error"
        assert "Failed to open camera 7." in message

    def test_predefined_arena_puts_detector_in_tracking(self, harness):
        harness.start()

        harness.svc.detector_service.configure_zones.assert_called_once_with(
            zone_data=harness.zone, width=640, height=480
        )
        harness.detector.set_context.assert_called_once_with("tracking")
        harness.detector.set_aquarium_region_defined.assert_called_once_with(True)
        harness.detector.set_single_subject_mode.assert_called_once_with(True)
        assert harness.svc._saved_detector_context == "calibration"
        assert harness.svc._arena_defined_event.is_set()

    def test_several_animals_disable_single_subject_mode(self, harness):
        harness.start(animals_per_aquarium=3)

        harness.detector.set_single_subject_mode.assert_called_once_with(False)

    def test_startup_statuses_are_published_in_order(self, harness):
        harness.start()

        assert harness.statuses() == [
            "⏳ Warming up camera...",
            "⏳ Loading detector...",
            "⏳ Starting capture...",
        ]

    def test_preview_status_after_start(self, harness):
        preview = MagicMock()
        harness.svc.preview_window = preview

        harness.start()

        preview.update_status_text.assert_called_with("⏳ Waiting for video...", color="orange")


class TestStartSessionAquariumDetection:
    def test_no_arena_without_validation_enters_detection_and_delays_recorder(
        self, tmp_path, monkeypatch
    ):
        h = _Harness(tmp_path, monkeypatch, polygon=False)
        preview = MagicMock()
        h.svc.preview_window = preview

        assert h.start(zones_validated=False) is True

        assert h.svc._aquarium_detection_phase is True
        assert h.recorder_calls == []
        assert not h.svc._arena_defined_event.is_set()
        h.detector.set_aquarium_region_defined.assert_called_once_with(False)
        zones_kwargs = h.detector.set_zones.call_args.kwargs
        assert zones_kwargs["zones"] == ZoneData()
        assert (zones_kwargs["actual_width"], zones_kwargs["actual_height"]) == (640, 480)
        preview.update_status_text.assert_called_with(
            "🔍 Looking for the aquarium...", color="yellow"
        )


class TestStartSessionDetectorRebuild:
    def test_changed_openvino_rebuilds_and_syncs_state(self, harness, monkeypatch):
        monkeypatch.setattr(
            harness.svc, "_resolve_session_detector_config", lambda: ("w.pt", True, "x")
        )
        seen: list[Any] = []

        def _init(**kwargs: Any) -> tuple[bool, Any]:
            seen.append((harness.svc.detector_service.detector, kwargs))
            harness.svc.detector_service.detector = harness.detector
            return True, harness.detector

        harness.svc.detector_service.initialize_detector.side_effect = _init

        assert harness.start() is True

        # The old detector is dropped BEFORE initialisation, so a new plugin is built.
        assert seen[0][0] is None
        assert seen[0][1]["use_openvino"] is True
        harness.svc.state_manager.update_detector_state.assert_called_once_with(
            source="live_camera_service.start_session",
            active_weight_name="w.pt",
            use_openvino=True,
        )

    def test_first_session_without_weight_syncs_only_openvino(self, harness):
        harness.svc.detector_service.detector = None
        harness.svc.detector_service.initialize_detector.return_value = (True, None)

        harness.start(record_video=False)

        harness.svc.state_manager.update_detector_state.assert_called_once_with(
            source="live_camera_service.start_session", use_openvino=False
        )

    def test_failed_initialisation_refuses_the_session(self, harness):
        harness.svc.detector_service.detector = None
        harness.svc.detector_service.initialize_detector.return_value = (False, None)

        assert harness.start() is False
        assert harness.recorder_calls == []

    def test_unchanged_config_reuses_the_loaded_detector(self, harness):
        harness.start()

        harness.svc.detector_service.initialize_detector.assert_not_called()


class TestStartSessionPreviewAndCountdown:
    def test_external_preview_is_created_with_index_and_duration(self, harness):
        harness.start(camera_index=2, duration_s=45.0, use_external_preview=True)

        assert harness.preview_calls == [(2, 45.0)]

    def test_controller_can_disable_the_external_preview(self, harness):
        harness.svc.controller = SimpleNamespace(_disable_live_preview_window=True)

        harness.start(use_external_preview=True)

        assert harness.preview_calls == []

    def test_countdown_without_root_sleeps_its_duration(self, harness, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(lsm_module.time, "sleep", slept.append)

        assert harness.start(use_countdown=True, countdown_duration_s=3) is True

        assert slept == [3]

    def test_zero_countdown_is_skipped(self, harness, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(lsm_module.time, "sleep", slept.append)

        harness.start(use_countdown=True, countdown_duration_s=0)

        assert slept == []

    def test_countdown_with_root_waits_for_the_callback(self, harness, monkeypatch):
        root = MagicMock()
        harness.svc.root = root
        pending: list[Any] = []
        harness.svc.recording_service._run_countdown.side_effect = (
            lambda seconds, done: pending.append((seconds, done))
        )
        pumps = {"n": 0}

        def _update() -> None:
            # The Tk loop runs twice, then the countdown window finishes.
            pumps["n"] += 1
            if pumps["n"] == 2:
                pending[0][1]()

        root.update.side_effect = _update
        monkeypatch.setattr(lsm_module.time, "sleep", lambda _s: None)
        preview = MagicMock()
        harness.svc.preview_window = preview

        assert harness.start(use_countdown=True, countdown_duration_s=4) is True

        assert pending[0][0] == 4
        assert pumps["n"] == 2
        preview.update_status_text.assert_any_call("⏳ Starting in 4s...", color="yellow")
        assert len(harness.recorder_calls) == 1

    def test_countdown_aborted_by_exit_event(self, harness, monkeypatch):
        root = MagicMock()
        harness.svc.root = root
        harness.svc.recording_service._run_countdown.side_effect = (
            lambda seconds, done: harness.svc.exit_event.set()
        )

        assert harness.start(use_countdown=True, countdown_duration_s=2) is False
        assert harness.recorder_calls == []

    def test_countdown_survives_a_dead_tk_root(self, harness, monkeypatch):
        root = MagicMock()
        root.update.side_effect = tk.TclError("application destroyed")
        harness.svc.root = root

        assert harness.start(use_countdown=True, countdown_duration_s=2) is True
        assert len(harness.recorder_calls) == 1


class _Thread:
    """Fake worker thread: alive for a scripted number of ``is_alive`` probes."""

    def __init__(self, alive_probes: int, alive_after_join: bool = False) -> None:
        self.alive_probes = alive_probes
        self.alive_after_join = alive_after_join
        self.joined: list[float | None] = []
        self.ident = None

    def is_alive(self) -> bool:
        if self.joined:
            return self.alive_after_join
        if self.alive_probes > 0:
            self.alive_probes -= 1
            return True
        return False

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)


class TestStopSession:
    def _stopping(self, harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> Any:
        svc = harness.svc
        svc._session_duration_s = 0.0
        svc.recorder.start_time = None
        monkeypatch.setattr(lsm_module.time, "sleep", lambda _s: None)
        return svc

    def test_timer_preview_camera_and_context_are_released(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        root = MagicMock()
        svc.root = root
        svc.timer_id = "after#7"
        preview = MagicMock()
        svc.preview_window = preview
        camera = MagicMock()
        svc.camera = camera
        svc._saved_detector_context = "calibration"

        assert svc.stop_session() is True

        root.after_cancel.assert_called_once_with("after#7")
        preview.destroy.assert_called_once_with()
        assert svc.preview_window is None
        assert svc._preview_window_destroyed is True
        camera.release.assert_called_once_with()
        assert svc.camera is None
        harness.detector.set_context.assert_called_once_with("calibration")
        assert svc._saved_detector_context is None
        svc.state_manager.update_processing_state.assert_called_once_with(
            source="live_camera_service.stop", is_processing=False
        )

    def test_tcl_errors_on_timer_and_preview_do_not_abort(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        root = MagicMock()
        root.after_cancel.side_effect = tk.TclError("bad id")
        svc.root = root
        svc.timer_id = "after#1"
        preview = MagicMock()
        preview.destroy.side_effect = tk.TclError("gone")
        svc.preview_window = preview

        assert svc.stop_session() is True
        assert svc.preview_window is None

    def test_context_restore_failure_still_clears_saved_context(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        svc._saved_detector_context = "weird"
        harness.detector.set_context.side_effect = ValueError("unknown context")

        assert svc.stop_session() is True
        assert svc._saved_detector_context is None

    def test_buttons_are_restored(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)

        svc.stop_session()

        buttons = [
            (c.args[0].data.button_name, c.args[0].data.state)
            for c in svc.event_bus.publish.call_args_list
            if c.args[0].type == UIEvents.UI_UPDATE_BUTTON_STATE
        ]
        assert buttons == [("start_rec", "normal"), ("stop_rec", "disabled")]

    def test_threads_that_finish_are_joined(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        processing = _Thread(alive_probes=2, alive_after_join=True)
        svc.processing_thread = processing  # type: ignore[assignment]

        svc.stop_session()

        # Waited out in ticks, then joined once with the residual budget.
        assert processing.joined == [0.5]
        # A normal end is not forced, even with a thread lingering after join.
        assert svc.recorder.stop_recording.call_args.kwargs == {}

    def test_hung_thread_forces_the_recorder_with_reason(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        svc._max_join_wait_s = 0.0
        hung = _Thread(alive_probes=10**6)
        svc.processing_thread = hung  # type: ignore[assignment]
        stopped: list[bool] = []
        svc.on_session_stopped = stopped.append

        svc.stop_session()

        svc.recorder.stop_recording.assert_called_once_with(force_stop=True, reason="thread_hang")
        # A hang is a machine problem, not a cancellation: the session is kept.
        assert stopped == [False]

    def test_cancelled_rmtree_failure_still_forgets_the_folder(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)
        svc.current_output_dir = harness.tmp_path / "live_x"
        svc.current_output_dir.mkdir()

        def _boom(_path: Any) -> None:
            raise PermissionError("locked by OneDrive")

        monkeypatch.setattr(lsm_module.shutil, "rmtree", _boom)

        assert svc.stop_session(cancelled=True) is True
        assert svc.current_output_dir is None

    def test_failing_stop_callback_is_swallowed(self, harness, monkeypatch):
        svc = self._stopping(harness, monkeypatch)

        def _callback(_cancelled: bool) -> None:
            raise RuntimeError("coordinator gone")

        svc.on_session_stopped = _callback

        assert svc.stop_session() is True


class TestFinishSessionEarly:
    def test_with_output_dir_runs_the_completion_path_keeping_data(self, harness, monkeypatch):
        calls: list[tuple[Path, bool]] = []
        monkeypatch.setattr(
            harness.svc,
            "_on_session_complete",
            lambda out, *, keep_data=False: calls.append((out, keep_data)),
        )
        harness.svc.current_output_dir = harness.tmp_path / "s"

        assert harness.svc.finish_session_early() is True
        assert calls == [(harness.tmp_path / "s", True)]

    def test_without_output_dir_stops_keeping_data(self, harness, monkeypatch):
        harness.intercept_stop(monkeypatch)
        harness.svc.current_output_dir = None

        assert harness.svc.finish_session_early() is True
        assert harness.stop_calls == [{"keep_data": True}]


class _ClosedRecorder:
    """A recorder whose clock can no longer be read."""

    @property
    def start_time(self) -> float:
        raise RuntimeError("closed")


class TestCancellationDetection:
    def test_early_automatic_stop_is_marked_cancelled(self, harness, monkeypatch):
        svc = harness.svc
        out = harness.tmp_path / "s"
        out.mkdir()
        svc.current_output_dir = out
        svc._session_duration_s = 60.0
        monkeypatch.setattr(lsm_module.time, "time", lambda: 1000.0)
        svc.recorder.start_time = 1000.0 - 29.0  # 29 s < 50 % of 60 s

        assert svc._detect_and_mark_cancellation() is True
        marker = (out / ".cancelled").read_text(encoding="utf-8")
        assert marker == "elapsed=29.0s\nplanned=60.0s\nforced=False\n"

    def test_stop_at_half_the_duration_is_not_cancelled(self, harness, monkeypatch):
        svc = harness.svc
        svc.current_output_dir = harness.tmp_path
        svc._session_duration_s = 60.0
        monkeypatch.setattr(lsm_module.time, "time", lambda: 1000.0)
        svc.recorder.start_time = 1000.0 - 30.0

        assert svc._detect_and_mark_cancellation() is False

    def test_short_sessions_use_a_five_second_floor(self, harness, monkeypatch):
        svc = harness.svc
        svc.current_output_dir = harness.tmp_path
        svc._session_duration_s = 6.0  # half is 3 s, the floor is 5 s
        monkeypatch.setattr(lsm_module.time, "time", lambda: 1000.0)
        svc.recorder.start_time = 1000.0 - 4.0

        assert svc._detect_and_mark_cancellation() is True

    def test_unreadable_start_time_is_not_a_cancellation(self, harness):
        svc = harness.svc
        svc.current_output_dir = harness.tmp_path
        svc._session_duration_s = 60.0
        svc.recorder = _ClosedRecorder()

        assert svc._detect_and_mark_cancellation() is False

    def test_forced_with_unreadable_start_time_still_cancels(self, harness):
        svc = harness.svc
        svc.current_output_dir = None
        svc.recorder = _ClosedRecorder()

        assert svc._detect_and_mark_cancellation(force=True) is True

    def test_keep_wins_over_force(self, harness):
        assert harness.svc._detect_and_mark_cancellation(force=True, keep=True) is False

    def test_marker_write_failure_is_not_fatal(self, harness):
        svc = harness.svc
        svc.current_output_dir = harness.tmp_path / "missing_dir"
        svc.recorder.start_time = None

        assert svc._detect_and_mark_cancellation(force=True) is True


class TestHungThreadStacks:
    def test_reports_only_live_threads(self):
        stop = threading.Event()
        worker = threading.Thread(target=stop.wait, daemon=True, name="hung-worker")
        worker.start()
        try:
            stacks = LiveSessionManagerMixin._hung_thread_stacks(
                [("alive", worker), ("none", None), ("dead", _Thread(alive_probes=0))],  # type: ignore[list-item]
            )
        finally:
            stop.set()
            worker.join(timeout=2)

        assert set(stacks) == {"alive"}
        assert "wait" in stacks["alive"]

    def test_live_thread_without_frame(self):
        stacks = LiveSessionManagerMixin._hung_thread_stacks(
            [("ghost", _Thread(alive_probes=5))]  # type: ignore[list-item]
        )

        assert stacks == {"ghost": "<frame unavailable>"}


class TestSessionFolderData:
    def test_unreadable_folder_is_assumed_to_hold_data(self, tmp_path, monkeypatch):
        folder = tmp_path / "exp_20260101_000000"
        folder.mkdir()

        def _deny(self: Path, _pattern: str) -> Any:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "glob", _deny)

        assert LiveSessionManagerMixin._session_folder_has_data(folder) is True

    def test_cleanup_survives_a_failed_removal(self, tmp_path, monkeypatch):
        service = DummyLiveService(tmp_path)
        leftover = tmp_path / "exp_20260101_000000"
        leftover.mkdir()

        def _boom(_path: Any) -> None:
            raise OSError("in use")

        monkeypatch.setattr(lsm_module.shutil, "rmtree", _boom)

        service._cleanup_existing_session_folders(tmp_path, "exp")

        assert leftover.exists()


class TestSessionTimerAndCountdown:
    def test_first_frame_schedules_the_timer_and_starts_preview(self, harness, monkeypatch):
        svc = harness.svc
        root = MagicMock()
        root.after.return_value = "after#3"
        svc.root = root
        svc._use_external_preview = True
        svc._session_duration_s = 12.5
        svc.current_output_dir = harness.tmp_path
        preview = MagicMock()
        svc.preview_window = preview
        completed: list[Path] = []
        monkeypatch.setattr(svc, "_on_session_complete", lambda out: completed.append(out))

        svc._on_session_active()

        delay, callback = root.after.call_args.args
        assert delay == 12500
        assert svc.timer_id == "after#3"
        preview.start_timer.assert_called_once_with()
        preview.update_status_text.assert_called_once_with("● Recording", color="red")
        callback()
        assert completed == [harness.tmp_path]

    def test_detection_phase_delays_the_timer(self, harness):
        svc = harness.svc
        root = MagicMock()
        svc.root = root
        svc._aquarium_detection_phase = True
        svc._session_duration_s = 10.0
        svc.current_output_dir = harness.tmp_path

        svc._on_session_active()

        root.after.assert_not_called()

    def test_integrated_canvas_gets_a_countdown(self, harness, monkeypatch):
        svc = harness.svc
        root = MagicMock()
        svc.root = root
        svc._use_external_preview = False
        svc._experiment_id = "CECT_4"
        monkeypatch.setattr(lsm_module.time, "time", lambda: 500.0)

        svc._setup_session_timer(20.0, harness.tmp_path)

        assert svc._session_start_time == 500.0
        events = [c.args[0] for c in svc.event_bus.publish.call_args_list]
        assert events[0].data.message == "● Recording: 0.0s / 20.0s (Remaining: 20.0s)"
        assert events[1].type == UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS
        assert events[1].data.progress_fraction == 0.0
        assert events[1].data.experiment_id == "CECT_4"
        # Re-armed every second.
        root.after.assert_any_call(1000, svc._update_session_countdown, 20.0)

    def test_countdown_reports_the_elapsed_fraction(self, harness, monkeypatch):
        svc = harness.svc
        svc.root = MagicMock()
        svc._experiment_id = "e"
        svc._session_start_time = 100.0
        monkeypatch.setattr(lsm_module.time, "time", lambda: 115.0)

        svc._update_session_countdown(60.0)

        status, task = (c.args[0] for c in svc.event_bus.publish.call_args_list)
        assert status.data.message == "● Recording: 15.0s / 60.0s (Remaining: 45.0s)"
        assert task.data.progress_fraction == pytest.approx(0.25)
        assert task.data.step == "Recording: 15s / 60s"

    def test_countdown_stops_when_time_is_up(self, harness, monkeypatch):
        svc = harness.svc
        svc.root = MagicMock()
        svc._session_start_time = 100.0
        monkeypatch.setattr(lsm_module.time, "time", lambda: 170.0)

        svc._update_session_countdown(60.0)

        svc.event_bus.publish.assert_not_called()
        svc.root.after.assert_not_called()

    @pytest.mark.parametrize("state", ["no_root", "exit", "no_start"])
    def test_countdown_is_inert_without_a_running_session(self, harness, state):
        svc = harness.svc
        svc.root = None if state == "no_root" else MagicMock()
        svc._session_start_time = None if state == "no_start" else 1.0
        if state == "exit":
            svc.exit_event.set()

        svc._update_session_countdown(60.0)

        svc.event_bus.publish.assert_not_called()


class TestStatusMessages:
    @pytest.mark.parametrize(
        ("lag", "expected"),
        [
            (1.0, "⏳ Analysing... (1.0s behind) - Recording OK"),
            (2.0, "⏳ Analysis is behind (2.0s) - Recording continues normally"),
            (4.9, "⏳ Analysis is behind (4.9s) - Recording continues normally"),
            (5.0, "⚠️ Analysis is far behind (5.0s) - Recording OK, analysis queued"),
        ],
    )
    def test_analysis_lag_bands(self, harness, lag, expected):
        harness.svc._publish_analysis_lag_status(lag)

        assert harness.statuses() == [expected]

    def test_lag_without_bus_is_silent(self, harness):
        harness.svc.event_bus = None  # type: ignore[assignment]

        harness.svc._publish_analysis_lag_status(9.0)

    def test_video_drop_singular_and_plural(self, harness):
        harness.svc._dropped_frames_video = 1
        harness.svc._publish_video_drop_status()
        harness.svc._dropped_frames_video = 12
        harness.svc._publish_video_drop_status()

        first, second = harness.statuses()
        assert first.startswith("⚠️ Video: 1 frame dropped")
        assert second.startswith("⚠️ Video: 12 frames dropped")

    def test_startup_repaint_failure_is_tolerated(self, harness):
        root = MagicMock()
        root.update_idletasks.side_effect = tk.TclError("destroyed")
        harness.svc.root = root

        harness.svc._publish_startup_status("x")

        assert harness.statuses() == ["x"]


def test_pytest_env_is_what_suppresses_the_camera_dialog():
    # The camera-failure dialog is gated on PYTEST_CURRENT_TEST; pin that the
    # variable exists here so the "outside pytest" test above is meaningful.
    assert os.environ.get("PYTEST_CURRENT_TEST")
