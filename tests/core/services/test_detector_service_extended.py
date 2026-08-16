"""
Extended unit tests for DetectorService in core/services/detector_service.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.services.detector_service import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_TRACK_THRESHOLD,
    DetectorService,
)
from zebtrack.settings import load_settings


class TestDetectorServiceExtended:
    """Test DetectorService tracker preference, config building, hyperparams, and definitions."""

    @pytest.fixture
    def service(self) -> DetectorService:
        settings_obj = load_settings()
        return DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=settings_obj,
        )

    def test_constants(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.80

    def test_resolve_single_subject_tracker_preference_from_project_data(
        self, service: DetectorService
    ):
        service.project_manager.project_data = {"tracking": {"use_single_subject_tracker": True}}
        assert service._resolve_single_subject_tracker_preference(None) is True

        service.project_manager.project_data = {"tracking": {"use_single_subject_tracker": False}}
        assert service._resolve_single_subject_tracker_preference(None) is False

    def test_resolve_single_subject_tracker_preference_none_fallback(
        self, service: DetectorService
    ):
        service.project_manager.project_data = {}
        assert service._resolve_single_subject_tracker_preference(None) is None
        assert service._resolve_single_subject_tracker_preference("single-video") is True

    def test_build_detector_config(self, service: DetectorService):
        plugin_mock = MagicMock()
        plugin_mock.conf_threshold = 0.35
        plugin_mock.nms_threshold = 0.50
        plugin_mock._context = "tracking"

        cfg_ov = service._build_detector_config(plugin_mock, use_openvino=True)
        assert cfg_ov["plugin_name"] == "OpenVINO"
        assert cfg_ov["conf_threshold"] == 0.35
        assert cfg_ov["nms_threshold"] == 0.50

        cfg_yolo = service._build_detector_config(plugin_mock, use_openvino=False)
        assert cfg_yolo["plugin_name"] == "YOLO (Ultralytics)"

    def test_set_single_subject_mode_delegates_to_detector(self, service: DetectorService):
        mock_detector = MagicMock()
        service.detector = mock_detector

        service.set_single_subject_mode(True)
        mock_detector.set_single_subject_mode.assert_called_once_with(True)

    def test_initialize_detector_no_model_path_returns_false(self, service: DetectorService):
        service.weight_manager.get_weight_path_by_method = MagicMock(return_value=None)  # type: ignore[method-assign]

        success, err = service.initialize_detector(animal_method="det")
        assert success is False
        assert "available" in str(err)

    def test_apply_project_detector_hyperparams(self, service: DetectorService):
        service.project_manager.project_data = {
            "model_overrides": {
                "confidence_threshold": 0.45,
                "nms_threshold": 0.65,
            }
        }
        plugin_mock = MagicMock()
        plugin_mock.conf_threshold = 0.25
        plugin_mock.nms_threshold = 0.45

        service._apply_project_detector_hyperparams(plugin_mock)
        assert plugin_mock.conf_threshold == 0.45
        assert plugin_mock.nms_threshold == 0.65

    def test_get_parameter_definitions(self, service: DetectorService):
        defs = service.get_parameter_definitions()
        assert "conf_threshold" in defs
        assert "nms_threshold" in defs
        assert "track_threshold" in defs
        assert defs["conf_threshold"] == "float"
        assert defs["use_bytetrack"] == "bool"
        assert defs["track_buffer"] == "int"

    def test_get_active_config(self, service: DetectorService):
        assert service.get_active_config() is None

        mock_detector = MagicMock()
        mock_detector.plugin.name = "best_seg.pt"
        service.detector = mock_detector
        assert service.get_active_config() == "best_seg.pt"
