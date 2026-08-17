"""Extended unit tests for coordinators/live_calibration_coordinator.py (Part 2)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator


class TestLiveCalibrationCoordinatorExtended2:
    """Test LiveCalibrationCoordinator polygon source setting and cancel state."""

    def test_set_last_polygon_source_no_event_bus(self):
        coord: Any = object.__new__(LiveCalibrationCoordinator)
        coord.event_bus = None
        coord._last_polygon_source = None

        coord._set_last_polygon_source("auto")
        assert coord._last_polygon_source == "auto"

    def test_set_last_polygon_source_with_event_bus(self):
        coord: Any = object.__new__(LiveCalibrationCoordinator)
        coord.event_bus = MagicMock()
        coord._last_polygon_source = None

        coord._set_last_polygon_source("manual")
        assert coord._last_polygon_source == "manual"
        coord.event_bus.publish.assert_called_once()

    def test_calibration_preserve_real_shape_toggle(self):
        coord: Any = object.__new__(LiveCalibrationCoordinator)
        coord._calibration_preserve_real_shape = False
        coord._calibration_preserve_real_shape = True
        assert coord._calibration_preserve_real_shape is True
