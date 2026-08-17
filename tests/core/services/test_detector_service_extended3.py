"""Extended unit tests for core/services/detector_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_TRACK_THRESHOLD,
    DetectorService,
)


class TestDetectorServiceExtended3:
    """Test DetectorService default thresholds, parameter definitions, and hyperparams."""

    def test_default_thresholds(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.80

    def test_initialize_detector_no_model_path(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        weight_mgr = MagicMock()
        weight_mgr.get_weight_path_by_method.return_value = None
        model_srv = MagicMock()
        settings = MagicMock()
        settings.model_selection.animal_method = "det"

        service = DetectorService(
            state_manager=state_mgr,
            project_manager=project_mgr,
            weight_manager=weight_mgr,
            model_service=model_srv,
            settings_obj=settings,
        )

        success, error_msg = service.initialize_detector(animal_method="det")
        assert success is False
        assert error_msg is not None
        assert "det" in error_msg

    def test_initialize_detector_weight_not_found_in_service(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        weight_mgr = MagicMock()
        weight_mgr.get_weight_path_by_method.return_value = "/weights/best_det.pt"
        model_srv = MagicMock()
        model_srv.find_weight_by_path.return_value = (None, None)
        settings = MagicMock()
        settings.model_selection.animal_method = "det"

        service = DetectorService(
            state_manager=state_mgr,
            project_manager=project_mgr,
            weight_manager=weight_mgr,
            model_service=model_srv,
            settings_obj=settings,
        )

        success, error_msg = service.initialize_detector(animal_method="det")
        assert success is False
        assert error_msg is not None
        assert "Could not find the weight" in error_msg

    def test_get_parameter_definitions(self):
        service = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )
        defs = service.get_parameter_definitions()
        assert defs["conf_threshold"] == "float"
        assert defs["nms_threshold"] == "float"
        assert defs["use_bytetrack"] == "bool"
        assert defs["track_threshold"] == "float"

    def test_get_available_configs_and_active_config(self):
        model_srv = MagicMock()
        model_srv.list_available_weights.return_value = ["w1.pt", "w2.pt"]

        service = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=model_srv,
            settings_obj=MagicMock(),
        )
        assert service.get_available_configs() == ["w1.pt", "w2.pt"]
        assert service.get_active_config() is None

    def test_apply_project_detector_hyperparams(self):
        project_mgr = MagicMock()
        project_mgr.project_data = {
            "model_overrides": {
                "confidence_threshold": 0.45,
                "nms_threshold": 0.55,
            }
        }
        service = DetectorService(
            state_manager=MagicMock(),
            project_manager=project_mgr,
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        plugin = MagicMock()
        plugin.conf_threshold = 0.25
        plugin.nms_threshold = 0.45

        service._apply_project_detector_hyperparams(plugin)
        assert plugin.conf_threshold == 0.45
        assert plugin.nms_threshold == 0.55
