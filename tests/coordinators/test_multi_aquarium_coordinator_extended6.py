"""Extended unit tests for coordinators/multi_aquarium_coordinator.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.multi_aquarium_coordinator import (
    MultiAquariumCoordinator,
    _payload_get,
)
from zebtrack.core.video.processing_mode import ProcessingMode


class TestMultiAquariumCoordinatorExtended6:
    """Test MultiAquariumCoordinator dependency injection, defaults, and payload helper."""

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
