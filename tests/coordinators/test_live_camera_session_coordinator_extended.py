"""Extended unit tests for coordinators/live_camera_session_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.live_camera_session_coordinator import (
    LIVE_PROFILE_TOOLTIP_FALLBACK,
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
    live_profile_display_default,
)


class TestLiveCameraSessionCoordinatorExtended:
    """Test LiveCameraSessionCoordinator constants, labels, state updates, and path resolution."""

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
