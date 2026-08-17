"""Extended unit tests for core/services/detector_service.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import DetectorService


class TestDetectorServiceExtended5:
    """Test DetectorService initialization error paths and plugin lookups."""

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
