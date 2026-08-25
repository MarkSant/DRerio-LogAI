"""Unit tests for ``core/recording/live_output_paths.py``.

Also covers the ``start_session`` fallback that consumes it — the branch that
used to resolve ``live_analysis_sessions/`` against the process working
directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.live_output_paths import (
    LIVE_SESSIONS_FOLDER_NAME,
    default_live_sessions_dir,
)
from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


class TestDefaultLiveSessionsDir:
    def test_is_absolute(self):
        """The whole point: never a CWD-relative path."""
        assert default_live_sessions_dir().is_absolute()

    def test_lives_under_the_user_home(self):
        assert Path.home() in default_live_sessions_dir().parents

    def test_keeps_the_historical_folder_name(self):
        assert default_live_sessions_dir().name == LIVE_SESSIONS_FOLDER_NAME

    def test_is_stable_across_calls(self):
        assert default_live_sessions_dir() == default_live_sessions_dir()


class StubService(LiveSessionManagerMixin):
    """Enough of LiveCameraService to reach the output-directory resolution."""

    def __init__(self):
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
        self.detector_service.initialize_detector.return_value = (True, MagicMock())
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

    # Stop right after the output directory is created.
    def _setup_camera(self, camera_index: int) -> bool:
        return True

    def _start_threads(self) -> bool:
        return False

    def set_last_detections(self, detections: list) -> None:
        pass


@pytest.fixture
def stub_service() -> StubService:
    return StubService()


class TestStartSessionOutputFallback:
    def test_without_project_or_override_uses_the_absolute_default(
        self, stub_service, tmp_path, monkeypatch
    ):
        fake_default = tmp_path / "home" / "ZebTrack" / LIVE_SESSIONS_FOLDER_NAME
        monkeypatch.setattr(
            "zebtrack.core.recording.live_session_manager.default_live_sessions_dir",
            lambda: fake_default,
        )

        started = stub_service.start_session(
            camera_index=0,
            duration_s=10.0,
            experiment_id="adhoc",
            record_video=False,
            zones_validated=True,
        )

        assert started is False  # _start_threads stub aborts the session
        assert stub_service.current_output_dir is not None
        assert stub_service.current_output_dir.parent == fake_default
        assert stub_service.current_output_dir.is_dir()

    def test_explicit_output_base_still_wins(self, stub_service, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "zebtrack.core.recording.live_session_manager.default_live_sessions_dir",
            lambda: tmp_path / "never_used",
        )
        chosen = tmp_path / "escolhida_pelo_usuario"

        stub_service.start_session(
            camera_index=0,
            duration_s=10.0,
            experiment_id="adhoc",
            record_video=False,
            output_base_dir=chosen,
            zones_validated=True,
        )

        assert stub_service.current_output_dir is not None
        assert stub_service.current_output_dir.parent == chosen
        assert not (tmp_path / "never_used").exists()
