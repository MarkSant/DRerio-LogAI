"""Extended unit tests for core/services/detector_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_TRACK_THRESHOLD,
    DetectorService,
)


class TestDetectorServiceExtended4:
    """Test DetectorService thresholds and model resolution guards."""

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
