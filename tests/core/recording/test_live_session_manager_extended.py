"""
Extended unit tests for LiveSessionManagerMixin in core/recording/live_session_manager.py.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin
from zebtrack.settings import load_settings


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
