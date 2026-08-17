"""Extended unit tests for coordinators/live_calibration_coordinator.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.coordinators.live_calibration_coordinator import (
    LiveCalibrationCoordinator,
    LiveCalibrationCoordinatorError,
)


class TestLiveCalibrationCoordinatorExtended:
    """Test LiveCalibrationCoordinator dependency injection, error classes, and attributes."""

    def test_error_class_inheritance(self):
        err = LiveCalibrationCoordinatorError("Calibration failed")
        assert str(err) == "Calibration failed"

    def test_live_calibration_coordinator_attributes(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        det_svc = MagicMock()
        wm = MagicMock()
        settings = MagicMock()
        event_bus = MagicMock()

        coord = LiveCalibrationCoordinator(
            state_manager=state_mgr,
            project_manager=pm,
            detector_service=det_svc,
            weight_manager=wm,
            settings_obj=settings,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is pm
        assert coord.detector_service is det_svc
        assert coord.weight_manager is wm
        assert coord.settings is settings
        assert coord.event_bus is event_bus

    def test_live_calibration_coordinator_default_event_bus(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        det_svc = MagicMock()
        wm = MagicMock()
        settings = MagicMock()

        coord = LiveCalibrationCoordinator(
            state_manager=state_mgr,
            project_manager=pm,
            detector_service=det_svc,
            weight_manager=wm,
            settings_obj=settings,
        )

        assert coord.event_bus is None
        assert coord._calibration_preserve_real_shape is False
        assert coord._last_calibration_cancelled is False
        assert coord._adhoc_zone_dir is None

    def test_on_project_manager_replaced(self):
        coord: Any = object.__new__(LiveCalibrationCoordinator)
        coord.project_manager = MagicMock()
        coord.event_bus = None
        coord._pending_zone_confirmation = False
        coord._last_polygon_source = None
        new_pm = MagicMock()

        coord._on_project_manager_replaced({"new_manager": new_pm})
        assert coord.project_manager is new_pm
