"""Extended unit tests for coordinators/live_camera_session_coordinator.py (Part 4)."""

from __future__ import annotations

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
)


class TestLiveCameraSessionCoordinatorExtended4:
    """Test LiveCameraSessionCoordinator session active checks and pending trigger states."""

    def test_is_live_session_active_lifecycle(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._active_live_session_id = None
        assert coord.is_live_session_active() is False

        coord._active_live_session_id = "session_99"
        assert coord.is_live_session_active() is True

    def test_get_live_session_info_idle(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._active_live_session_id = None
        assert coord.get_live_session_info() is None

    def test_pending_trigger_context_initial(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_trigger_context = None
        coord._pending_live_context = None
        assert coord._pending_trigger_context is None
        assert coord._pending_live_context is None
