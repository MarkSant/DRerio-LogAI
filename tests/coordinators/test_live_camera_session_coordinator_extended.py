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


class TestLiveCameraSessionCoordinatorExtended:
    def test_constants_and_labels(self):
        assert LIVE_PROFILE_TOOLTIP_FALLBACK == "default"
        label = live_profile_display_default()
        assert "default" in label

    def test_error_class(self):
        err = LiveCameraSessionCoordinatorError("Session failed")
        assert isinstance(err, Exception)
        assert str(err) == "Session failed"

    def test_resolve_session_paths_override_and_no_project(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord.project_manager = MagicMock()
        coord.project_manager.project_path = None

        # 1. Explicit override
        out_dir, folder = coord._resolve_session_paths(override="/custom/out")
        assert out_dir == "/custom/out"
        assert folder is None

        # 2. No project path
        out_none, folder_none = coord._resolve_session_paths()
        assert out_none is None
        assert folder_none is None

    def test_on_project_manager_replaced(self):
        coord = object.__new__(LiveCameraSessionCoordinator)
        coord._pending_live_context = {"exp": 1}
        coord._pending_live_kind = "project"
        coord._active_live_session_id = "session_1"

        new_proj_mgr = MagicMock()
        coord._on_project_manager_replaced({"new_manager": new_proj_mgr})

        assert coord.project_manager is new_proj_mgr
        assert coord._pending_live_context is None
        assert coord._pending_live_kind is None
        assert coord._active_live_session_id is None


class TestLiveCameraSessionCoordinatorExtended2:
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


class TestLiveCameraSessionCoordinatorExtended3:
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


class TestLiveCameraSessionCoordinatorExtended4:
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


class TestLiveCameraSessionCoordinatorExtended5:
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


class TestLiveCameraSessionCoordinatorExtended6:
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


class TestLiveCameraSessionCoordinatorExtended7:
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
