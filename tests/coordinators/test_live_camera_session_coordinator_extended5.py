"""Extended unit tests for coordinators/live_camera_session_coordinator.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator


class TestLiveCameraSessionCoordinatorExtended5:
    """Test LiveCameraSessionCoordinator dependency attributes and optional batch coordinator."""

    def test_live_camera_session_coordinator_attributes(self):
        state_mgr = MagicMock()
        live_svc = MagicMock()
        pm = MagicMock()
        det_svc = MagicMock()
        settings = MagicMock()
        cal_coord = MagicMock()
        batch_coord = MagicMock()

        coord = LiveCameraSessionCoordinator(
            state_manager=state_mgr,
            live_camera_service=live_svc,
            project_manager=pm,
            detector_service=det_svc,
            settings_obj=settings,
            live_calibration_coordinator=cal_coord,
            live_batch_coordinator=batch_coord,
        )

        assert coord.live_camera_service is live_svc
        assert coord.project_manager is pm
        assert coord.detector_service is det_svc
        assert coord.settings is settings
        assert coord.live_calibration_coordinator is cal_coord
        assert coord.live_batch_coordinator is batch_coord
