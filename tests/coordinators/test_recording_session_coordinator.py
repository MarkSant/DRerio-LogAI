from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.recording_session_coordinator import (
    CoordinatorValidationError,
    RecordingSessionCoordinator,
)


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_recording_service():
    return MagicMock()


@pytest.fixture
def mock_live_camera_service():
    return MagicMock()


@pytest.fixture
def mock_project_manager():
    pm = MagicMock()
    pm.project_path = "test/path"
    pm.project_data = {}
    return pm


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.camera.index = 0
    return s


@pytest.fixture
def mock_live_calibration_coordinator():
    cc = MagicMock()
    cc.ensure_zones_before_recording.return_value = True
    cc.pending_zone_confirmation = False
    return cc


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def mock_arduino_manager():
    return MagicMock()


@pytest.fixture
def coordinator(
    mock_state_manager,
    mock_recording_service,
    mock_live_camera_service,
    mock_project_manager,
    mock_settings,
    mock_live_calibration_coordinator,
    mock_event_bus,
    mock_arduino_manager,
):
    return RecordingSessionCoordinator(
        state_manager=mock_state_manager,
        recording_service=mock_recording_service,
        live_camera_service=mock_live_camera_service,
        project_manager=mock_project_manager,
        settings_obj=mock_settings,
        live_calibration_coordinator=mock_live_calibration_coordinator,
        event_bus=mock_event_bus,
        arduino_manager=mock_arduino_manager,
    )


def test_validate_dependencies_success(coordinator):
    assert coordinator.validate_dependencies() is True


def test_validate_dependencies_missing_recording_service(coordinator):
    coordinator.recording_service = None
    with pytest.raises(CoordinatorValidationError):
        coordinator.validate_dependencies()


def test_validate_dependencies_missing_live_camera_service(coordinator):
    coordinator.live_camera_service = None
    with pytest.raises(CoordinatorValidationError):
        coordinator.validate_dependencies()


def test_validate_dependencies_missing_project_manager(coordinator):
    coordinator.project_manager = None
    with pytest.raises(CoordinatorValidationError):
        coordinator.validate_dependencies()


def test_start_recording_with_explicit_context(coordinator):
    context = {
        "output_folder": "test/out",
        "folder_name": "test_folder",
        "experiment_id": "test_exp",
        "duration": 300,
    }

    result = coordinator.start_recording(context=context)

    assert result is True
    coordinator.recording_service.schedule_recording.assert_called_once()
    assert coordinator.state_manager.update_state.call_count > 0


def test_start_recording_no_context_with_path(coordinator):
    result = coordinator.start_recording(output_path="test/out", experiment_id="test_exp")

    assert result is True
    coordinator.recording_service.schedule_recording.assert_called_once()


def test_start_recording_zones_not_validated(coordinator):
    coordinator.live_calibration_coordinator.ensure_zones_before_recording.return_value = False

    result = coordinator.start_recording(output_path="test/out", experiment_id="test_exp")

    assert result is False
    coordinator.recording_service.schedule_recording.assert_not_called()


def test_start_recording_zones_pending_confirmation(coordinator):
    coordinator.live_calibration_coordinator.ensure_zones_before_recording.return_value = False
    coordinator.live_calibration_coordinator.pending_zone_confirmation = True

    result = coordinator.start_recording(output_path="test/out", experiment_id="test_exp")

    assert result is False
    assert coordinator._pending_recording_context is not None


def test_stop_recording_success(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = True
    coordinator.state_manager.get_recording_state.return_value = recording_state

    result = coordinator.stop_recording()

    assert result is True
    coordinator.recording_service.stop_session.assert_called_once()


def test_stop_recording_not_recording(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = False
    coordinator.state_manager.get_recording_state.return_value = recording_state

    result = coordinator.stop_recording()

    assert result is False
    coordinator.recording_service.stop_session.assert_not_called()


def test_is_recording(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = True
    coordinator.state_manager.get_recording_state.return_value = recording_state

    assert coordinator.is_recording() is True


def test_get_recording_info(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = True
    recording_state.output_path = "test/path"
    recording_state.experiment_id = "test_exp"
    recording_state.duration = 300
    coordinator.state_manager.get_recording_state.return_value = recording_state

    info = coordinator.get_recording_info()

    assert info is not None
    assert info["is_recording"] is True
    assert info["output_path"] == "test/path"


def test_get_recording_info_not_recording(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = False
    coordinator.state_manager.get_recording_state.return_value = recording_state

    assert coordinator.get_recording_info() is None


@patch("zebtrack.core.services.external_trigger_gate.decide_external_trigger")
def test_handle_external_trigger_reject(mock_decide, coordinator):
    from zebtrack.core.services.external_trigger_gate import ExternalTriggerDecision

    mock_decide.return_value = ExternalTriggerDecision.REJECT_NO_ARDUINO

    result = coordinator._handle_external_trigger({}, False)

    assert result is True
    assert coordinator._pending_external_trigger is None


@patch("zebtrack.core.services.external_trigger_gate.decide_external_trigger")
def test_handle_external_trigger_arm(mock_decide, coordinator):
    from zebtrack.core.services.external_trigger_gate import ExternalTriggerDecision

    mock_decide.return_value = ExternalTriggerDecision.ARM_AND_WAIT

    context = {"folder_name": "test"}
    result = coordinator._handle_external_trigger(context, True)

    assert result is True
    assert coordinator._pending_external_trigger is context


def test_trigger_recording(coordinator):
    context = {"output_folder": "test", "folder_name": "test"}
    coordinator._pending_external_trigger = context

    coordinator.trigger_recording(1)

    assert coordinator._pending_external_trigger is None
    coordinator.recording_service.schedule_recording.assert_called_once()


def test_trigger_recording_no_pending(coordinator):
    coordinator._pending_external_trigger = None

    coordinator.trigger_recording(1)

    coordinator.recording_service.schedule_recording.assert_not_called()


def test_on_arduino_event_start(coordinator):
    context = {"output_folder": "test", "folder_name": "test"}
    coordinator._pending_external_trigger = context

    coordinator.on_arduino_event(1)

    assert coordinator._pending_external_trigger is None
    coordinator.recording_service.schedule_recording.assert_called_once()


def test_on_arduino_event_stop(coordinator):
    recording_state = MagicMock()
    recording_state.is_recording = True
    coordinator.state_manager.get_recording_state.return_value = recording_state

    coordinator.on_arduino_event(0)

    coordinator.recording_service.stop_session.assert_called_once()


def test_schedule_recording_live_analysis(coordinator):
    context = {"is_live_analysis": True, "output_folder": "test"}
    coordinator.live_camera_service.start_session.return_value = True

    coordinator._schedule_recording(context, {}, trigger_source="manual")

    coordinator.live_camera_service.start_session.assert_called_once()
    assert coordinator.state_manager.update_state.call_count > 0


def test_on_zone_saved(coordinator):
    context = {"output_folder": "test", "folder_name": "test"}
    coordinator._pending_recording_context = context
    coordinator.live_calibration_coordinator.pending_zone_confirmation = True

    coordinator._on_zone_saved()

    coordinator.recording_service.schedule_recording.assert_called_once()
