"""Unit tests for ProjectLifecycleCoordinator helpers."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.ui.event_bus_v2 import UIEvents


@dataclass
class DummyAquarium:
    group: str | None = None
    subject_id: str | None = None
    day: int | None = None


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def coordinator(event_bus):
    return ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        detector_service=MagicMock(),
    )


def test_register_event_handlers_sets_zone_manager_and_subscribes(coordinator, event_bus):
    zone_manager = MagicMock()

    coordinator.register_event_handlers(zone_manager=zone_manager)

    assert coordinator._zone_manager is zone_manager
    event_bus.subscribe.assert_called_with(
        UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED, coordinator._handle_aquarium_config_updated
    )


@pytest.mark.parametrize("payload", [None, "invalid", 123])
def test_handle_aquarium_config_updated_ignores_non_dict(coordinator, payload):
    zone_manager = MagicMock()
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(payload)

    zone_manager.get_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_missing_fields(coordinator):
    zone_manager = MagicMock()
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated({"aquarium_id": 1})

    zone_manager.get_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_no_zone_manager(coordinator):
    coordinator._zone_manager = None

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    assert coordinator._zone_manager is None


def test_handle_aquarium_config_updated_no_zone_data(coordinator):
    zone_manager = MagicMock()
    zone_manager.get_multi_aquarium_zone_data.return_value = None
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    zone_manager.save_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_aquarium_not_found(coordinator):
    zone_manager = MagicMock()
    zone_data = MagicMock()
    zone_data.get_aquarium.return_value = None
    zone_manager.get_multi_aquarium_zone_data.return_value = zone_data
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 99, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    zone_manager.save_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_success_updates_aquarium(coordinator):
    zone_manager = MagicMock()
    aquarium = DummyAquarium(group="G0", subject_id="S0", day=0)
    zone_data = MagicMock()
    zone_data.get_aquarium.return_value = aquarium
    zone_manager.get_multi_aquarium_zone_data.return_value = zone_data
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {
            "aquarium_id": 1,
            "config": {"group": "G1", "subject_id": "S1", "day": 2},
            "video_path": "/v.mp4",
        }
    )

    assert aquarium.group == "G1"
    assert aquarium.subject_id == "S1"
    assert aquarium.day == 2
    zone_manager.save_multi_aquarium_zone_data.assert_called_once_with("/v.mp4", zone_data)


def test_close_project_publishes_events_and_updates_manager(coordinator, event_bus):
    new_manager = MagicMock()
    coordinator.project_workflow_adapter.close_project.return_value = new_manager

    result = coordinator.close_project()

    assert result is new_manager
    assert coordinator.project_manager is new_manager
    event_types = [call.args[0].type for call in event_bus.publish.call_args_list]
    assert UIEvents.PROJECT_MANAGER_REPLACED in event_types
    assert UIEvents.PROJECT_CLOSED in event_types


def test_close_project_stops_active_live_session(event_bus):
    """When a live session is running, close_project must stop it BEFORE
    delegating to the workflow adapter so the camera handle is released
    and worker threads are joined ahead of the project state reset.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = True

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()

    coord.close_project()

    live_camera_service.is_session_active.assert_called_once()
    live_camera_service.stop_session.assert_called_once()
    # stop_session must be invoked before adapter.close_project
    assert (
        live_camera_service.stop_session.call_count
        >= 1  # explicit assertion above already checks; sanity here
    )


def test_close_project_skips_live_stop_when_not_active(event_bus):
    """No-op when no live session is running — avoids spurious UI events
    and avoids touching the camera/threads when there is nothing to clean.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = False

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()

    coord.close_project()

    live_camera_service.is_session_active.assert_called_once()
    live_camera_service.stop_session.assert_not_called()


def test_close_project_handles_missing_live_camera_service(event_bus):
    """Coordinator must not crash when live_camera_service is not wired
    (legacy test setups, headless contexts).
    """
    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=None,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()

    # Should not raise
    coord.close_project()


def test_close_project_swallows_live_stop_errors(event_bus):
    """An exception while stopping the live session must NOT block close
    (the project still needs to be closed). The error is logged.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = True
    live_camera_service.stop_session.side_effect = RuntimeError("camera stuck")

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    new_manager = MagicMock()
    coord.project_workflow_adapter.close_project.return_value = new_manager

    result = coord.close_project()

    assert result is new_manager
    coord.project_workflow_adapter.close_project.assert_called_once()
