"""Tests for batch context and processing mode helpers (Phase 4 decomposition).

Batch context → ProgressTrackingCoordinator
Multi-aquarium state/mode → MultiAquariumCoordinator
"""

from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator


@pytest.fixture
def progress_coordinator():
    """Create a ProgressTrackingCoordinator for batch context tests."""
    return ProgressTrackingCoordinator(
        state_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        cancel_event=Event(),
        event_bus=MagicMock(),
        view=None,
        root=None,
    )


@pytest.fixture
def multi_aquarium_coordinator():
    """Create a MultiAquariumCoordinator for mode/state tests."""
    return MultiAquariumCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=Event(),
        video_classification_service=MagicMock(),
        event_bus=MagicMock(),
        view=None,
        root=None,
        detector=None,
    )


def test_reset_multi_aquarium_state_clears_flags(multi_aquarium_coordinator):
    multi_aquarium_coordinator._auto_assign_aquariums = True
    multi_aquarium_coordinator._last_assignment_configs = [{"a": 1}]
    multi_aquarium_coordinator._assigned_videos = {"/v1.mp4", "/v2.mp4"}

    multi_aquarium_coordinator.reset_multi_aquarium_state()

    assert multi_aquarium_coordinator._auto_assign_aquariums is False
    assert multi_aquarium_coordinator._last_assignment_configs is None
    assert multi_aquarium_coordinator._assigned_videos == set()


def test_batch_context_flow(progress_coordinator):
    progress_coordinator._init_batch_context(total_videos=3)

    assert progress_coordinator._is_batch_processing() is True

    progress_coordinator._update_batch_context(completed=True)
    progress_coordinator._update_batch_context(failed=True)

    summary = progress_coordinator._finalize_batch_context()

    assert summary["total"] == 3
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert progress_coordinator._is_batch_processing() is False


@patch("zebtrack.core.zone_manager.ZoneManager")
def test_apply_processing_mode_to_video_updates_and_persists(
    mock_zone_manager_cls, multi_aquarium_coordinator
):
    multi_data = MagicMock(sequential_processing=False)
    multi_aquarium_coordinator.project_manager.get_multi_aquarium_zone_data.return_value = (
        multi_data
    )
    multi_aquarium_coordinator.project_manager.find_video_entry.return_value = {
        "path": "/v.mp4",
        "multi_aquarium_zone_data": {},
    }
    mock_zone_manager_cls.multi_aquarium_zone_data_to_dict.return_value = {"serialized": True}

    multi_aquarium_coordinator._apply_processing_mode_to_video("/v.mp4", sequential=True)

    assert multi_data.sequential_processing is True
    multi_aquarium_coordinator.project_manager.save_project.assert_called_once()


@patch("zebtrack.core.zone_manager.ZoneManager")
def test_apply_processing_mode_to_video_no_data(mock_zone_manager_cls, multi_aquarium_coordinator):
    multi_aquarium_coordinator.project_manager.get_multi_aquarium_zone_data.return_value = None

    multi_aquarium_coordinator._apply_processing_mode_to_video("/v.mp4", sequential=True)

    multi_aquarium_coordinator.project_manager.save_project.assert_not_called()


def test_apply_processing_mode_to_all_videos_saves_for_each(multi_aquarium_coordinator):
    multi_aquarium_coordinator.project_manager.get_all_videos.return_value = [
        {"path": "/v1.mp4"},
        {"path": "/v2.mp4"},
    ]
    multi_aquarium_coordinator._apply_processing_mode_to_video = MagicMock()

    multi_aquarium_coordinator._apply_processing_mode_to_all_videos(sequential=True)

    assert multi_aquarium_coordinator._apply_processing_mode_to_video.call_count == 2


def test_on_processing_mode_changed_apply_current_video(multi_aquarium_coordinator):
    multi_aquarium_coordinator._apply_processing_mode_to_video = MagicMock()

    multi_aquarium_coordinator._on_processing_mode_changed(
        {"sequential": False, "video_path": "/active.mp4"}
    )

    multi_aquarium_coordinator._apply_processing_mode_to_video.assert_called_once_with(
        "/active.mp4", sequential=False
    )
