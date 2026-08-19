"""Extended unit tests for coordinators/live_calibration_coordinator.py (Part 3)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator


class TestLiveCalibrationCoordinatorExtended3:
    """Test LiveCalibrationCoordinator project manager replacement and polygon clearing."""

    def test_on_project_manager_replaced_updates_reference(self):
        coord: Any = object.__new__(LiveCalibrationCoordinator)
        coord.project_manager = MagicMock()
        coord.event_bus = None
        coord._last_polygon_source = "manual"

        new_pm = MagicMock()
        coord._on_project_manager_replaced({"new_manager": new_pm})

        assert coord.project_manager is new_pm
        assert coord._last_polygon_source is None
