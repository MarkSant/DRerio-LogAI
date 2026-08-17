"""Extended unit tests for core/services/detector_service.py (Part 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import DetectorService


class TestDetectorServiceExtended8:
    """Test DetectorService services injection and weight manager access."""

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
