"""Extended unit tests for coordinators/live_camera_session_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.base_coordinator import CoordinatorError
from zebtrack.coordinators.live_camera_session_coordinator import (
    LIVE_PROFILE_TOOLTIP_FALLBACK,
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
    live_profile_display_default,
)


class TestLiveCameraSessionCoordinatorExtended2:
    """Test LiveCameraSessionCoordinator constants, exceptions, and profile display."""

    def test_constants_and_exceptions(self):
        assert LIVE_PROFILE_TOOLTIP_FALLBACK == "default"
        assert issubclass(LiveCameraSessionCoordinatorError, CoordinatorError)

    def test_live_profile_display_default(self):
        res = live_profile_display_default()
        assert "default" in res or "padrão" in res

    def test_coordinator_initialization(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        detector_srv = MagicMock()
        live_srv = MagicMock()
        settings = MagicMock()
        live_calib = MagicMock()
        event_bus = MagicMock()

        coord = LiveCameraSessionCoordinator(
            state_manager=state_mgr,
            live_camera_service=live_srv,
            project_manager=project_mgr,
            detector_service=detector_srv,
            settings_obj=settings,
            live_calibration_coordinator=live_calib,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is project_mgr
        assert coord.detector_service is detector_srv
        assert coord.live_camera_service is live_srv
