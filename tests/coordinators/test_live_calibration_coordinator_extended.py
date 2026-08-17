"""Extended unit tests for coordinators/live_calibration_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_calibration_coordinator import (
    LiveCalibrationCoordinator,
    LiveCalibrationCoordinatorError,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


class TestLiveCalibrationCoordinatorExtended:
    """Test LiveCalibrationCoordinator exceptions, state resets, polygon source
    updates, and camera release.
    """

    def test_coordinator_error_inheritance(self):
        err = LiveCalibrationCoordinatorError("Calibration failed")
        assert isinstance(err, Exception)
        assert str(err) == "Calibration failed"

    def test_on_project_manager_replaced_state_clearance(self):
        coord = object.__new__(LiveCalibrationCoordinator)
        coord._pending_zone_confirmation = True
        coord._session_count = 5
        coord._last_calibration_cancelled = True
        coord._last_polygon_source = "auto"
        coord._set_last_polygon_source = MagicMock()  # type: ignore[assignment]
        coord._adhoc_zone_dir = "/tmp/adhoc"

        new_mgr = MagicMock()
        coord._on_project_manager_replaced({"new_manager": new_mgr})

        assert coord.project_manager is new_mgr
        assert coord._pending_zone_confirmation is False
        assert coord._session_count == 0
        assert coord._last_calibration_cancelled is False
        coord._set_last_polygon_source.assert_called_once_with(None)
        assert coord._adhoc_zone_dir is None

    def test_set_last_polygon_source_emits_event(self):
        event_bus = EventBusV2()
        coord = object.__new__(LiveCalibrationCoordinator)
        coord.event_bus = event_bus
        coord._last_polygon_source = None

        events_received = []
        event_bus.subscribe(
            UIEvents.LIVE_POLYGON_SOURCE_CHANGED,
            lambda e: events_received.append(e),
        )

        coord._set_last_polygon_source("auto")
        assert coord._last_polygon_source == "auto"
        assert len(events_received) == 1

    def test_release_calibration_camera(self):
        coord = object.__new__(LiveCalibrationCoordinator)
        mock_camera = MagicMock()
        mock_stopped = MagicMock()
        mock_camera._stopped = mock_stopped
        coord.camera = mock_camera

        coord._release_calibration_camera("dialog_rejected")
        mock_stopped.set.assert_called_once()
        mock_camera.release.assert_called_once()
        assert coord.camera is None

    def test_release_calibration_camera_when_none(self):
        coord = object.__new__(LiveCalibrationCoordinator)
        coord.camera = None
        # Should not throw
        coord._release_calibration_camera("no_op")
        assert coord.camera is None
