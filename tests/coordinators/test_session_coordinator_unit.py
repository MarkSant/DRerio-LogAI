"""Unit tests for SessionCoordinator small helpers."""

from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.base_coordinator import CoordinatorValidationError
from zebtrack.coordinators.session_coordinator import SessionCoordinator
from zebtrack.ui.events import Events


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish_event = MagicMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def state_manager():
    manager = MagicMock()
    manager.get_recording_state.return_value = None
    return manager


@pytest.fixture
def settings_obj():
    settings = MagicMock()
    settings.camera = MagicMock(index=0)
    return settings


@pytest.fixture
def project_manager():
    manager = MagicMock()
    manager.project_data = {}
    return manager


@pytest.fixture
def coordinator(state_manager, project_manager, settings_obj, event_bus):
    return SessionCoordinator(
        state_manager=state_manager,
        recording_service=MagicMock(),
        live_camera_service=MagicMock(),
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=settings_obj,
        event_bus=event_bus,
        arduino_manager=MagicMock(),
        live_batch_coordinator=None,
        root=None,
        view=None,
    )


@pytest.mark.parametrize(
    "missing_attr",
    ["recording_service", "live_camera_service", "project_manager"],
)
def test_validate_dependencies_missing_raises(
    state_manager, project_manager, settings_obj, event_bus, missing_attr
):
    services = {
        "recording_service": MagicMock(),
        "live_camera_service": MagicMock(),
        "project_manager": project_manager,
    }
    services[missing_attr] = None

    coordinator = SessionCoordinator(
        state_manager=state_manager,
        recording_service=services["recording_service"],
        live_camera_service=services["live_camera_service"],
        project_manager=services["project_manager"],
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=settings_obj,
        event_bus=event_bus,
        arduino_manager=MagicMock(),
        live_batch_coordinator=None,
        root=None,
        view=None,
    )

    with pytest.raises(CoordinatorValidationError):
        coordinator.validate_dependencies()


def test_validate_dependencies_success(coordinator):
    assert coordinator.validate_dependencies() is True


def test_is_recording_false_when_no_state(coordinator, state_manager):
    state_manager.get_recording_state.return_value = None

    assert coordinator.is_recording() is False


def test_is_recording_true(coordinator, state_manager):
    state_manager.get_recording_state.return_value = MagicMock(is_recording=True)

    assert coordinator.is_recording() is True


def test_get_recording_info_none_when_not_recording(coordinator, state_manager):
    state_manager.get_recording_state.return_value = MagicMock(is_recording=False)

    assert coordinator.get_recording_info() is None


def test_get_recording_info_returns_dict(coordinator, state_manager):
    state_manager.get_recording_state.return_value = MagicMock(
        is_recording=True,
        output_path="/tmp/out",
        experiment_id="exp1",
        duration=120,
    )

    info = coordinator.get_recording_info()

    assert info == {
        "is_recording": True,
        "output_path": "/tmp/out",
        "experiment_id": "exp1",
        "duration": 120,
    }


def test_handle_external_trigger_no_arduino_publishes_error(
    coordinator, project_manager, event_bus
):
    project_manager.project_data = {"external_trigger_mode": True}
    context = {
        "folder_name": "D1_G1_S1",
        "day": 1,
        "group": "G1",
        "cobaia": "S1",
        "arduino_port": "COM3",
    }

    waiting = coordinator._handle_external_trigger(context, arduino_enabled=False)

    assert waiting is True
    event_bus.publish_event.assert_called_with(
        Events.UI_SHOW_ERROR,
        {
            "title": "Trigger Externo Indisponível",
            "message": "O modo de trigger externo exige um Arduino configurado.",
        },
    )


def test_handle_external_trigger_with_arduino_sets_pending(coordinator, project_manager, event_bus):
    project_manager.project_data = {"external_trigger_mode": True}
    context = {
        "folder_name": "D1_G1_S1",
        "day": 1,
        "group": "G1",
        "cobaia": "S1",
        "arduino_port": "COM3",
    }

    waiting = coordinator._handle_external_trigger(context, arduino_enabled=True)

    assert waiting is True
    assert coordinator._pending_external_trigger == context
    calls = [call.args[0] for call in event_bus.publish_event.call_args_list]
    assert Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE in calls
    assert Events.UI_SET_STATUS in calls


def test_handle_external_trigger_disabled_returns_false(coordinator, project_manager, event_bus):
    project_manager.project_data = {"external_trigger_mode": False}

    waiting = coordinator._handle_external_trigger({"folder_name": "D1"}, arduino_enabled=True)

    assert waiting is False
    assert coordinator._pending_external_trigger is None
    event_bus.publish_event.assert_not_called()


def test_clear_external_trigger_wait_clears_and_updates_ui(coordinator, event_bus):
    coordinator._pending_external_trigger = {"folder_name": "D1"}

    coordinator._clear_external_trigger_wait()

    assert coordinator._pending_external_trigger is None
    calls = [call.args[0] for call in event_bus.publish_event.call_args_list]
    assert Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE in calls
    assert Events.UI_UPDATE_BUTTON_STATE in calls
    assert Events.UI_SET_STATUS in calls


def test_clear_pending_recording_context_removes_attributes(coordinator):
    coordinator._pending_recording_context = {"folder_name": "D1"}
    coordinator._pending_recording_project_data = {"use_arduino": False}
    coordinator._pending_recording_trigger_source = "manual"

    coordinator._clear_pending_recording_context()

    assert not hasattr(coordinator, "_pending_recording_context")
    assert not hasattr(coordinator, "_pending_recording_project_data")
    assert not hasattr(coordinator, "_pending_recording_trigger_source")


def test_increment_session_count_and_has_recorded_before(coordinator):
    assert coordinator._has_recorded_before() is False

    coordinator._increment_session_count()

    assert coordinator._has_recorded_before() is True

    coordinator._increment_session_count()

    assert coordinator._session_count == 2
