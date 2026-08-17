"""Extended unit tests for core/services/detector_service.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import DetectorService


class TestDetectorServiceExtended7:
    """Test DetectorService detector instance status and readiness."""

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
