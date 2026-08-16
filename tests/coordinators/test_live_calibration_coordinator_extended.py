"""Extended unit tests for LiveCalibrationCoordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_calibration_coordinator import (
    LiveCalibrationCoordinator,
    LiveCalibrationCoordinatorError,
)
from zebtrack.settings import load_settings


class TestLiveCalibrationCoordinatorExtended:
    """Test exception hierarchy, coordinator initialization, and project replacement."""

    def test_exception_hierarchy(self):
        err = LiveCalibrationCoordinatorError("calibration failed")
        assert isinstance(err, Exception)
        assert str(err) == "calibration failed"

    def test_coordinator_initialization(self):
        state_mgr = MagicMock()
        proj_mgr = MagicMock()
        det_svc = MagicMock()
        weight_mgr = MagicMock()
        settings = load_settings()
        event_bus = MagicMock()

        coord = LiveCalibrationCoordinator(
            state_manager=state_mgr,
            project_manager=proj_mgr,
            detector_service=det_svc,
            weight_manager=weight_mgr,
            settings_obj=settings,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is proj_mgr
        assert coord.detector_service is det_svc
        assert coord.weight_manager is weight_mgr
        assert coord.settings is settings
        assert coord.event_bus is event_bus
        assert coord._pending_zone_confirmation is False
        assert coord._session_count == 0
        assert coord._last_polygon_source is None

    def test_on_project_manager_replaced_drops_session_state(self):
        state_mgr = MagicMock()
        old_proj_mgr = MagicMock()
        new_proj_mgr = MagicMock()
        det_svc = MagicMock()
        weight_mgr = MagicMock()
        settings = load_settings()
        event_bus = MagicMock()

        coord = LiveCalibrationCoordinator(
            state_manager=state_mgr,
            project_manager=old_proj_mgr,
            detector_service=det_svc,
            weight_manager=weight_mgr,
            settings_obj=settings,
            event_bus=event_bus,
        )

        coord._pending_zone_confirmation = True
        coord._session_count = 5
        coord._last_calibration_cancelled = True
        coord._adhoc_zone_dir = "/tmp/adhoc"

        coord._on_project_manager_replaced({"new_manager": new_proj_mgr})

        assert coord.project_manager is new_proj_mgr
        assert coord._pending_zone_confirmation is False
        assert coord._session_count == 0
        assert coord._last_calibration_cancelled is False
        assert coord._adhoc_zone_dir is None
