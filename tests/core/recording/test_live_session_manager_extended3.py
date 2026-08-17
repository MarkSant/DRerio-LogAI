"""Extended unit tests for core/recording/live_session_manager.py."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


class DummyLiveService(LiveSessionManagerMixin):
    def __init__(self):
        self.project_workflow_service: Any = None
        self.project_manager: Any = None
        self.settings = MagicMock()
        self._analysis_params: dict = {}
        self.capture_thread: Any = None
        self.processing_thread: Any = None
        self.video_recording_thread: Any = None


class TestLiveSessionManagerExtended3:
    """Test LiveSessionManagerMixin config resolution, active checks, and folder cleanup."""

    def test_resolve_session_detector_config_with_project(self):
        svc = DummyLiveService()
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
        svc = DummyLiveService()
        svc.project_manager = MagicMock()
        svc.project_manager.project_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
        }

        assert svc._resolve_calibration_perspective() == "lateral"

    def test_resolve_calibration_perspective_from_analysis_params(self):
        svc = DummyLiveService()
        svc.project_manager = None
        svc._analysis_params = {"behavioral_analysis": {"aquarium_perspective": "top_down"}}

        assert svc._resolve_calibration_perspective() == "top_down"

    def test_is_session_active_lifecycle(self):
        svc = DummyLiveService()
        assert svc.is_session_active() is False

        mock_t = MagicMock(spec=threading.Thread)
        mock_t.is_alive.return_value = True
        svc.processing_thread = mock_t

        assert svc.is_session_active() is True

    def test_cleanup_existing_session_folders_missing_base(self, tmp_path: Path):
        svc = DummyLiveService()
        non_existent = tmp_path / "does_not_exist"
        # Should return safely without raising
        svc._cleanup_existing_session_folders(non_existent, "exp_1")

    def test_cleanup_existing_session_folders_matching_dirs(self, tmp_path: Path):
        svc = DummyLiveService()
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
