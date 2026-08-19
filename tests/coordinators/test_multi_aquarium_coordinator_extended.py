"""Extended unit tests for coordinators/multi_aquarium_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.coordinators.multi_aquarium_coordinator import (
    MultiAquariumCoordinator,
    _payload_get,
)
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.ui.payloads import ZoneProcessingModeChangedPayload


class TestMultiAquariumCoordinatorExtended:
    def test_payload_get_dict_and_object(self):
        # Dict
        d = {"key": "val", "num": 10}
        assert _payload_get(d, "key") == "val"
        assert _payload_get(d, "missing", "default") == "default"

        # Object
        payload = ZoneProcessingModeChangedPayload(sequential=True)
        assert _payload_get(payload, "sequential") is True
        assert _payload_get(payload, "non_existent", "fallback") == "fallback"

    def test_reset_multi_aquarium_state(self):
        mock_sm = MagicMock()
        mock_pm = MagicMock()
        mock_ds = MagicMock()
        mock_sett = MagicMock()
        mock_ui = MagicMock()
        mock_uic = MagicMock()
        mock_ce = MagicMock()
        mock_vcs = MagicMock()

        coord = MultiAquariumCoordinator(
            state_manager=mock_sm,
            project_manager=mock_pm,
            detector_service=mock_ds,
            settings_obj=mock_sett,
            ui_coordinator=mock_ui,
            ui_state_controller=mock_uic,
            cancel_event=mock_ce,
            video_classification_service=mock_vcs,
        )

        coord._auto_assign_aquariums = True
        coord._last_assignment_configs = [{"id": 1}]
        coord._assigned_videos.add("/v.mp4")

        coord.reset_multi_aquarium_state()
        assert coord._auto_assign_aquariums is False
        assert coord._last_assignment_configs is None
        assert len(coord._assigned_videos) == 0

    def test_on_processing_mode_changed_dispatches_to_video(self):
        mock_sm = MagicMock()
        mock_pm = MagicMock()
        mock_ds = MagicMock()
        mock_sett = MagicMock()
        mock_ui = MagicMock()
        mock_uic = MagicMock()
        mock_ce = MagicMock()
        mock_vcs = MagicMock()

        coord = MultiAquariumCoordinator(
            state_manager=mock_sm,
            project_manager=mock_pm,
            detector_service=mock_ds,
            settings_obj=mock_sett,
            ui_coordinator=mock_ui,
            ui_state_controller=mock_uic,
            cancel_event=mock_ce,
            video_classification_service=mock_vcs,
        )

        with patch.object(coord, "_apply_processing_mode_to_video") as mock_apply:
            payload = {"sequential": True, "video_path": "/path/video.mp4"}
            coord._on_processing_mode_changed(payload)
            mock_apply.assert_called_once_with("/path/video.mp4", sequential=True)

    def test_on_processing_mode_changed_dispatches_to_all(self):
        mock_sm = MagicMock()
        mock_pm = MagicMock()
        mock_ds = MagicMock()
        mock_sett = MagicMock()
        mock_ui = MagicMock()
        mock_uic = MagicMock()
        mock_ce = MagicMock()
        mock_vcs = MagicMock()

        coord = MultiAquariumCoordinator(
            state_manager=mock_sm,
            project_manager=mock_pm,
            detector_service=mock_ds,
            settings_obj=mock_sett,
            ui_coordinator=mock_ui,
            ui_state_controller=mock_uic,
            cancel_event=mock_ce,
            video_classification_service=mock_vcs,
        )

        with patch.object(coord, "_apply_processing_mode_to_all_videos") as mock_apply_all:
            payload = {"sequential": False}
            coord._on_processing_mode_changed(payload)
            mock_apply_all.assert_called_once_with(sequential=False)


class TestMultiAquariumCoordinatorExtended6:
    def test_payload_get_dict_and_object(self):
        d = {"video_path": "/path/v1.mp4", "count": 2}
        assert _payload_get(d, "video_path") == "/path/v1.mp4"
        assert _payload_get(d, "count") == 2
        assert _payload_get(d, "nonexistent", 0) == 0

    def test_multi_aquarium_coordinator_init_state(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        det_svc = MagicMock()
        settings = MagicMock()
        ui_coord = MagicMock()
        ui_ctrl = MagicMock()
        cancel_evt = MagicMock()
        vid_cls = MagicMock()

        coord = MultiAquariumCoordinator(
            state_manager=state_mgr,
            project_manager=pm,
            detector_service=det_svc,
            settings_obj=settings,
            ui_coordinator=ui_coord,
            ui_state_controller=ui_ctrl,
            cancel_event=cancel_evt,
            video_classification_service=vid_cls,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is pm
        assert coord.detector_service is det_svc
        assert coord.settings is settings
        assert coord._active_processing_mode == ProcessingMode.MULTI_TRACK
        assert coord._is_detecting_aquarium is False
        assert coord._auto_assign_aquariums is False
        assert coord._assigned_videos == set()
