"""Extended unit tests for core/recording/live_session_manager.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


class TestLiveSessionManagerExtended2:
    """Test LiveSessionManagerMixin config resolution, perspective, and session status."""

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
