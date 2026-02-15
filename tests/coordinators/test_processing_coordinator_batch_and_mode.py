"""Tests for ProcessingCoordinator batch context and processing mode helpers."""

from threading import Event
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator


class DummyMultiAquariumData:
    def __init__(self, sequential_processing: bool):
        self.sequential_processing = sequential_processing


@pytest.fixture
def coordinator():
    return ProcessingCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=Event(),
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        analysis_service=MagicMock(),
        recorder_factory=MagicMock(),
        event_bus=MagicMock(),
        view=None,
        root=None,
        detector=None,
    )


def test_reset_multi_aquarium_state_clears_flags(coordinator):
    coordinator._auto_assign_aquariums = True
    coordinator._last_assignment_configs = [{"a": 1}]
    coordinator._assigned_videos = {"/v1.mp4", "/v2.mp4"}

    coordinator.reset_multi_aquarium_state()

    assert coordinator._auto_assign_aquariums is False
    assert coordinator._last_assignment_configs is None
    assert coordinator._assigned_videos == set()


def test_batch_context_flow(coordinator):
    coordinator._init_batch_context(total_videos=3)

    assert coordinator._is_batch_processing() is True

    coordinator._update_batch_context("/v1.mp4", success=True)
    coordinator._update_batch_context("/v2.mp4", success=False)

    summary = coordinator._finalize_batch_context()

    assert summary == {
        "total": 3,
        "successful": 1,
        "failed": 1,
        "successful_videos": ["/v1.mp4"],
        "failed_videos": ["/v2.mp4"],
    }
    assert coordinator._is_batch_processing() is False


def test_apply_processing_mode_to_video_updates_and_persists(coordinator):
    multi_data = DummyMultiAquariumData(sequential_processing=False)
    coordinator.project_manager.get_multi_aquarium_zone_data.return_value = multi_data

    changed = coordinator._apply_processing_mode_to_video("/v.mp4", sequential=True)

    assert changed is True
    assert multi_data.sequential_processing is True
    coordinator.project_manager.save_multi_aquarium_zone_data.assert_called_once_with(
        "/v.mp4", multi_data, persist=True
    )


def test_apply_processing_mode_to_video_no_change(coordinator):
    multi_data = DummyMultiAquariumData(sequential_processing=True)
    coordinator.project_manager.get_multi_aquarium_zone_data.return_value = multi_data

    changed = coordinator._apply_processing_mode_to_video("/v.mp4", sequential=True)

    assert changed is False
    coordinator.project_manager.save_multi_aquarium_zone_data.assert_not_called()


def test_apply_processing_mode_to_all_videos_saves_once(coordinator):
    coordinator.project_manager.project_data = {
        "videos": [
            {"path": "/v1.mp4"},
            {"path": "/v2.mp4"},
        ]
    }
    coordinator.project_manager.project_path = "/project"
    coordinator._apply_processing_mode_to_video = MagicMock(side_effect=[True, False])

    coordinator._apply_processing_mode_to_all_videos(sequential=True)

    coordinator.project_manager.save_project.assert_called_once()


def test_on_processing_mode_changed_apply_current_video(coordinator):
    coordinator.project_manager.get_active_zone_video.return_value = "/active.mp4"
    coordinator._apply_processing_mode_to_video = MagicMock(return_value=True)

    coordinator._on_processing_mode_changed({"sequential": False, "apply_to_all": False})

    coordinator._apply_processing_mode_to_video.assert_called_once_with("/active.mp4", False)
