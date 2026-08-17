"""Extended unit tests for core/recording/live_session_manager.py (Part 4)."""

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
        self._arena_defined_event = threading.Event()
        self.current_output_dir: Path | None = None
        self.capture_thread = None
        self.processing_thread = None
        self.video_recording_thread = None


class TestLiveSessionManagerExtended4:
    """Test LiveSessionManagerMixin detector resolution fallback and active session state."""

    def test_resolve_session_detector_config_settings_fallback(self):
        svc = DummyLiveService()
        svc.project_manager = None
        svc.settings.model_selection.use_openvino = True

        weight, openvino, source = svc._resolve_session_detector_config()
        assert weight is None
        assert openvino is True
        assert source == "settings"

    def test_arena_defined_event_initial(self):
        svc = DummyLiveService()
        assert svc._arena_defined_event.is_set() is False
        svc._arena_defined_event.set()
        assert svc._arena_defined_event.is_set() is True

    def test_resolve_calibration_perspective(self):
        svc = DummyLiveService()
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
        svc = DummyLiveService()
        assert svc.is_session_active() is False

        mock_th = MagicMock(spec=threading.Thread)
        mock_th.is_alive.return_value = True
        svc.capture_thread = mock_th
        assert svc.is_session_active() is True
