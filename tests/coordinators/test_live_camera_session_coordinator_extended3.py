"""Extended unit tests for coordinators/live_camera_session_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
)


class TestLiveCameraSessionCoordinatorExtended3:
    """Test LiveCameraSessionCoordinator stop and delegate calls."""

    def test_stop_live_session_delegates_to_service(self):
        state_mgr = MagicMock()
        event_bus = MagicMock()
        live_srv = MagicMock()
        proj_mgr = MagicMock()
        det_srv = MagicMock()
        batch_coord = MagicMock()
        calib_coord = MagicMock()
        settings = MagicMock()

        coord = LiveCameraSessionCoordinator(
            state_manager=state_mgr,
            event_bus=event_bus,
            live_camera_service=live_srv,
            project_manager=proj_mgr,
            detector_service=det_srv,
            live_batch_coordinator=batch_coord,
            live_calibration_coordinator=calib_coord,
            settings_obj=settings,
        )
        coord._active_live_session_id = "session_123"

        coord.stop_live_session()
        live_srv.stop_session.assert_called_once_with(cancelled=True)

    def test_stop_live_session_when_idle_returns_false(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._active_live_session_id = None

        assert coord.stop_live_session() is False

    def test_has_pending_external_trigger(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_trigger_context = None
        assert coord.has_pending_external_trigger() is False

        coord._pending_trigger_context = {"armed": True}
        assert coord.has_pending_external_trigger() is True

    def test_clear_pending_external_trigger(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord.event_bus = None
        coord._pending_trigger_context = {"armed": True}
        coord.clear_pending_external_trigger()
        assert coord._pending_trigger_context is None
