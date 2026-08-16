"""Extended unit tests for LiveCameraSessionCoordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import (
    LIVE_PROFILE_TOOLTIP_FALLBACK,
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
    live_profile_display_default,
)


class TestLiveCameraSessionCoordinatorExtended:
    """Test live profile display fallback, error hierarchy, and coordinator properties."""

    def test_live_profile_display_default_and_fallback(self):
        assert LIVE_PROFILE_TOOLTIP_FALLBACK == "default"
        label = live_profile_display_default()
        assert "default" in label.lower()

    def test_live_camera_session_coordinator_error(self):
        err = LiveCameraSessionCoordinatorError("camera disconnected")
        assert isinstance(err, Exception)
        assert str(err) == "camera disconnected"

    def test_coordinator_initial_state(self):
        state_manager = MagicMock()
        live_service = MagicMock()
        live_service.is_session_active = False
        project_manager = MagicMock()
        detector_service = MagicMock()
        settings_obj = MagicMock()
        live_calib = MagicMock()
        event_bus = MagicMock()

        coord = LiveCameraSessionCoordinator(
            state_manager=state_manager,
            live_camera_service=live_service,
            project_manager=project_manager,
            detector_service=detector_service,
            settings_obj=settings_obj,
            live_calibration_coordinator=live_calib,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_manager
        assert coord.live_camera_service is live_service
        assert coord._pending_live_context is None
        assert coord._pending_trigger_context is None
