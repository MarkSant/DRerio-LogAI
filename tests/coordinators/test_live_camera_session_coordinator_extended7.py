"""Extended unit tests for coordinators/live_camera_session_coordinator.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
    live_profile_display_default,
)


class TestLiveCameraSessionCoordinatorExtended7:
    """Test LiveCameraSessionCoordinator initialization state and coordinator wiring."""

    def test_live_camera_session_coordinator_init(self):
        state_mgr = MagicMock()
        live_cam_svc = MagicMock()
        pm = MagicMock()
        det_svc = MagicMock()
        settings = MagicMock()
        calib_coord = MagicMock()
        event_bus = MagicMock()

        coord = LiveCameraSessionCoordinator(
            state_manager=state_mgr,
            live_camera_service=live_cam_svc,
            project_manager=pm,
            detector_service=det_svc,
            settings_obj=settings,
            live_calibration_coordinator=calib_coord,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_mgr
        assert coord.live_camera_service is live_cam_svc
        assert coord.project_manager is pm
        assert coord.detector_service is det_svc
        assert coord.settings is settings
        assert coord.event_bus is event_bus
        assert coord._pending_live_context is None
        assert coord._pending_live_kind is None

    def test_live_profile_display_default(self):
        label = live_profile_display_default()
        assert isinstance(label, str)
        assert len(label) > 0

    def test_live_camera_session_coordinator_error_inheritance(self):
        err = LiveCameraSessionCoordinatorError("Session failed")
        assert str(err) == "Session failed"

    def test_live_camera_session_coordinator_pending_kind_assignment(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_live_kind = "grid"
        assert coord._pending_live_kind == "grid"
