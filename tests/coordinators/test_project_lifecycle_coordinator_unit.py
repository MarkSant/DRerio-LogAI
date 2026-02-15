"""Unit tests for ProjectLifecycleCoordinator helpers."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.ui.events import Events


@dataclass
class DummyAquarium:
    group: str | None = None
    subject_id: str | None = None
    day: int | None = None


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish_event = MagicMock()
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
        Events.ZONE_AQUARIUM_CONFIG_UPDATED, coordinator._handle_aquarium_config_updated
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
    calls = [call.args[0] for call in event_bus.publish_event.call_args_list]
    assert Events.PROJECT_MANAGER_REPLACED in calls
    assert Events.PROJECT_CLOSED in calls
