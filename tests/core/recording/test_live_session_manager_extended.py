"""
Extended unit tests for LiveSessionManagerMixin in core/recording/live_session_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin
from zebtrack.settings import load_settings


class DummyLiveService(LiveSessionManagerMixin):
    """Concrete test harness implementing LiveSessionManagerMixin."""

    def __init__(self, tmp_path: Path):
        self.settings = load_settings()
        self.project_manager = MagicMock()
        self.project_workflow_service = MagicMock()
        self.state_manager = MagicMock()
        self.detector_service = MagicMock()
        self.recording_service = MagicMock()
        self.event_bus = MagicMock()
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None
        self._analysis_params = {}


class TestLiveSessionManagerExtended:
    """Test LiveSessionManagerMixin session helpers, cleanup, and status."""

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
