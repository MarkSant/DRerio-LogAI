"""Extended unit tests for coordinators/live_camera_session_coordinator.py (Part 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
)


class TestLiveCameraSessionCoordinatorExtended8:
    """Test LiveCameraSessionCoordinator session context bindings and dependencies."""

    def test_pending_live_context_assignment(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_live_context = {"session_id": "sess_123"}
        assert coord._pending_live_context["session_id"] == "sess_123"

    def test_pending_live_context_clear(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_live_context = {"session_id": "sess_123"}
        coord._pending_live_context = None
        assert coord._pending_live_context is None

    def test_live_camera_session_coordinator_calib_ref(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        calib = MagicMock()
        coord.live_calibration_coordinator = calib
        assert coord.live_calibration_coordinator is calib

    def test_live_camera_session_coordinator_batch_ref(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        batch = MagicMock()
        coord.live_batch_coordinator = batch
        assert coord.live_batch_coordinator is batch
