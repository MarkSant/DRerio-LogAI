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


class TestDetectorServiceThresholdsAndValidation:
    def test_default_threshold_constants(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.80

    def test_update_tracking_parameters_validates_conf_threshold_range(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="conf_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(conf_threshold=1.5)

        with pytest.raises(ValueError, match="conf_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(conf_threshold=-0.1)

    def test_update_tracking_parameters_validates_nms_threshold_range(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="nms_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(nms_threshold=1.2)

    def test_update_tracking_parameters_validates_track_buffer(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="track_buffer must be at least 1"):
            svc.update_tracking_parameters(track_buffer=0)

        with pytest.raises(ValueError, match="track_buffer must be an integer"):
            svc.update_tracking_parameters(track_buffer="not_an_int")  # type: ignore[arg-type]

    def test_update_tracking_parameters_with_plugin(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )
        mock_plugin = MagicMock()
        mock_plugin.conf_threshold = 0.25
        mock_plugin.nms_threshold = 0.45

        mock_detector = MagicMock()
        mock_detector.plugin = mock_plugin
        svc.detector = mock_detector

        result = svc.update_tracking_parameters(
            conf_threshold=0.6,
            nms_threshold=0.5,
            scope="global",
        )
        assert result is True
        assert mock_plugin.conf_threshold == 0.6
        assert mock_plugin.nms_threshold == 0.5


class TestDetectorServiceExtended3:
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


class TestDetectorServiceExtended4:
    def test_default_thresholds(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.80

    def test_initialize_detector_no_model_path(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        weight_mgr = MagicMock()
        model_srv = MagicMock()
        settings = MagicMock()

        svc = DetectorService(
            state_manager=state_mgr,
            project_manager=project_mgr,
            weight_manager=weight_mgr,
            model_service=model_srv,
            settings_obj=settings,
        )

        weight_mgr.get_weight_path_by_method.return_value = None
        success, err = svc.initialize_detector(
            animal_method="seg",
            use_openvino=False,
            active_weight_name="nonexistent.pt",
        )

        assert success is False
        assert err is not None
        assert "available for animal detection" in err

    def test_initialize_detector_weight_not_found(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        weight_mgr = MagicMock()
        model_srv = MagicMock()
        settings = MagicMock()

        svc = DetectorService(
            state_manager=state_mgr,
            project_manager=project_mgr,
            weight_manager=weight_mgr,
            model_service=model_srv,
            settings_obj=settings,
        )

        weight_mgr.get_weight_path_by_method.return_value = "/path/to/missing.pt"
        model_srv.find_weight_by_path.return_value = (None, None)

        success, err = svc.initialize_detector(
            animal_method="det",
            use_openvino=False,
            active_weight_name="missing.pt",
        )

        assert success is False
        assert err is not None
        assert "Could not find the weight" in err


class TestDetectorServiceExtended5:
    def test_initialize_detector_no_model_path(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        weight_manager.get_weight_path_by_method.return_value = None
        model_service = MagicMock()
        settings = MagicMock()
        settings.model_selection.animal_method = "seg"

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )
        success, error = service.initialize_detector(animal_method="seg")

        assert success is False
        assert error is not None
        assert "available" in error or "modelo" in error or "model" in error

    def test_initialize_detector_weight_not_found_in_model_service(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        weight_manager.get_weight_path_by_method.return_value = "/models/fish.pt"
        model_service = MagicMock()
        model_service.find_weight_by_path.return_value = (None, None)
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )
        success, error = service.initialize_detector(animal_method="det")

        assert success is False
        assert error is not None
        assert "matching the path" in error or "weight" in error or "peso" in error

    def test_initialize_detector_openvino_model_path_missing(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        weight_manager.get_weight_path_by_method.return_value = "/models/fish.pt"
        model_service = MagicMock()
        model_service.find_weight_by_path.return_value = ("fish.pt", {"type": "det"})
        model_service.get_model_path_for_inference.return_value = (None, None)
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )
        success, error = service.initialize_detector(animal_method="det", use_openvino=True)

        assert success is False
        assert error is not None
        assert "OpenVINO" in error


class TestDetectorServiceExtended6:
    def test_set_single_subject_mode_with_detector(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )

        mock_detector = MagicMock()
        service.detector = mock_detector

        service.set_single_subject_mode(True)
        mock_detector.set_single_subject_mode.assert_called_once_with(True)

        service.set_single_subject_mode(False)
        mock_detector.set_single_subject_mode.assert_called_with(False)

    def test_set_single_subject_mode_no_detector(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )
        service.detector = None
        # Should return safely
        service.set_single_subject_mode(True)


class TestDetectorServiceExtended7:
    def test_detector_service_detector_none_by_default(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )

        assert service.detector is None

    def test_detector_service_detector_status_no_detector(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )

        assert service.detector is None
        assert service.model_service is model_service


class TestDetectorServiceExtended8:
    def test_detector_service_injected_services(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        wm = MagicMock()
        model_svc = MagicMock()
        settings = MagicMock()

        svc = DetectorService(
            state_manager=state_mgr,
            project_manager=pm,
            weight_manager=wm,
            model_service=model_svc,
            settings_obj=settings,
        )

        assert svc.state_manager is state_mgr
        assert svc.project_manager is pm
        assert svc.weight_manager is wm
        assert svc.settings is settings

    def test_detector_service_model_service_ref(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        wm = MagicMock()
        model_svc = MagicMock()
        settings = MagicMock()

        svc = DetectorService(
            state_manager=state_mgr,
            project_manager=pm,
            weight_manager=wm,
            model_service=model_svc,
            settings_obj=settings,
        )

        assert svc.model_service is model_svc
