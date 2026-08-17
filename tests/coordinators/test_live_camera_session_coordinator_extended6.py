"""Extended unit tests for coordinators/live_camera_session_coordinator.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator


class TestLiveCameraSessionCoordinatorExtended6:
    """Test LiveCameraSessionCoordinator pending publication and project manager replacement."""

    def test_publish_pending_no_event_bus(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord.event_bus = None

        coord._publish_pending({"experiment_id": "exp_01"})

    def test_publish_pending_with_event_bus(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord.event_bus = MagicMock()
        coord.live_calibration_coordinator = MagicMock()
        coord.live_calibration_coordinator.last_polygon_source = "auto"

        ctx = {"experiment_id": "exp_01", "group": "Control", "day": 1, "subject": "1"}
        coord._publish_pending(ctx)

        coord.event_bus.publish.assert_called_once()

    def test_on_project_manager_replaced(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord.project_manager = MagicMock()
        new_pm = MagicMock()

        coord._on_project_manager_replaced({"new_manager": new_pm})
        assert coord.project_manager is new_pm

    def test_on_resume_requested_no_pending_context(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_live_context = None
        coord._pending_live_kind = None

        # Should return without raising errors
        coord._on_resume_requested()
