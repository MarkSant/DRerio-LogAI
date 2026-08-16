from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_project_manager():
    pm = MagicMock()
    pm.project_path = "test/path"
    pm.project_data = {}
    return pm


@pytest.fixture
def mock_project_workflow_service():
    service = MagicMock()
    service.create_project.return_value = {
        "success": True,
        "error_message": None,
        "animal_method": "zebrafish",
        "wizard_metadata": {},
    }
    return service


@pytest.fixture
def mock_project_workflow_adapter():
    adapter = MagicMock()
    adapter.close_project.return_value = MagicMock()
    adapter.open_project_workflow.return_value = True
    return adapter


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.model_selection.use_openvino = False
    return s


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def mock_detector_service():
    ds = MagicMock()
    ds.initialize_detector.return_value = (True, "")
    return ds


@pytest.fixture
def mock_model_override_service():
    return MagicMock()


@pytest.fixture
def mock_calibration_coordinator():
    return MagicMock()


@pytest.fixture
def mock_live_camera_service():
    cs = MagicMock()
    cs.is_session_active.return_value = False
    return cs


@pytest.fixture
def coordinator(
    mock_state_manager,
    mock_project_manager,
    mock_project_workflow_service,
    mock_project_workflow_adapter,
    mock_settings,
    mock_event_bus,
    mock_detector_service,
    mock_model_override_service,
    mock_calibration_coordinator,
    mock_live_camera_service,
):
    return ProjectLifecycleCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        project_workflow_service=mock_project_workflow_service,
        project_workflow_adapter=mock_project_workflow_adapter,
        settings_obj=mock_settings,
        event_bus=mock_event_bus,
        detector_service=mock_detector_service,
        model_override_service=mock_model_override_service,
        calibration_coordinator=mock_calibration_coordinator,
        live_camera_service=mock_live_camera_service,
    )


def test_register_event_handlers(coordinator):
    mock_zone_manager = MagicMock()
    coordinator.register_event_handlers(zone_manager=mock_zone_manager)

    assert coordinator._zone_manager == mock_zone_manager
    coordinator.event_bus.subscribe.assert_any_call(
        UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED,
        coordinator._handle_aquarium_config_updated,
    )


def test_close_project(coordinator):
    coordinator._stop_live_session_if_active = MagicMock()

    new_pm = coordinator.close_project()

    coordinator._stop_live_session_if_active.assert_called_once()
    coordinator.project_workflow_adapter.close_project.assert_called_once()
    assert coordinator.project_manager == new_pm


def test_create_project_success(coordinator):
    result = coordinator.create_project(use_openvino=True, active_weight="test_weight")

    assert result is True
    coordinator.project_workflow_service.create_project.assert_called_once()
    coordinator.detector_service.initialize_detector.assert_called_once()


def test_create_project_failure_service(coordinator):
    coordinator.project_workflow_service.create_project.return_value = {
        "success": False,
        "error_message": "test error",
    }

    result = coordinator.create_project()

    assert result is False
    coordinator.detector_service.initialize_detector.assert_not_called()


def test_create_project_failure_detector(coordinator):
    coordinator.detector_service.initialize_detector.return_value = (False, "error")

    result = coordinator.create_project()

    assert result is False


def test_open_project_success(coordinator):
    result = coordinator.open_project(project_path="test/path")

    assert result is True
    coordinator.project_workflow_adapter.open_project_workflow.assert_called_once()


def test_open_project_failure(coordinator):
    coordinator.project_workflow_adapter.open_project_workflow.return_value = False

    result = coordinator.open_project(project_path="test/path")

    assert result is False


def test_can_remove_project_asset(coordinator):
    coordinator.project_manager.can_remove_asset.return_value = (True, None)

    result, error = coordinator.can_remove_project_asset("video.mp4", "arena")

    assert result is True
    assert error is None
    coordinator.project_manager.can_remove_asset.assert_called_once()


def test_delete_project_asset(coordinator):
    coordinator.project_manager.remove_asset.return_value = True

    result = coordinator.delete_project_asset("video.mp4", "arena")

    assert result is True
    coordinator.project_manager.remove_asset.assert_called_once()


def test_delete_hierarchy_node_group(coordinator):
    coordinator.project_manager.remove_group.return_value = (1, 0)

    removed, failed = coordinator.delete_hierarchy_node("group", group_id="g1")

    assert removed == 1
    assert failed == 0
    coordinator.project_manager.remove_group.assert_called_once_with("g1", delete_files=True)


def test_delete_hierarchy_node_day(coordinator):
    coordinator.project_manager.remove_day.return_value = (1, 0)

    removed, failed = coordinator.delete_hierarchy_node("day", group_id="g1", day_id="d1")

    assert removed == 1
    assert failed == 0
    coordinator.project_manager.remove_day.assert_called_once_with("g1", "d1", delete_files=True)


def test_delete_hierarchy_node_subject(coordinator):
    coordinator.project_manager.remove_subject.return_value = (1, 0)

    removed, failed = coordinator.delete_hierarchy_node(
        "subject", group_id="g1", day_id="d1", subject_id="s1"
    )

    assert removed == 1
    assert failed == 0
    coordinator.project_manager.remove_subject.assert_called_once_with(
        "g1", "d1", "s1", delete_files=True
    )


def test_delete_aquarium_scope(coordinator):
    coordinator.project_manager.remove_aquarium_scope.return_value = True

    result = coordinator.delete_aquarium_scope("video.mp4", 1)

    assert result is True
    coordinator.project_manager.remove_aquarium_scope.assert_called_once()


def test_clear_aquarium_subject(coordinator):
    coordinator.project_manager.clear_aquarium_subject.return_value = True

    result = coordinator.clear_aquarium_subject("video.mp4", 1)

    assert result is True
    coordinator.project_manager.clear_aquarium_subject.assert_called_once()


def test_reset_analysis_data(coordinator):
    coordinator.project_manager.reset_analysis_data.return_value = True

    result = coordinator.reset_analysis_data("video.mp4")

    assert result is True
    coordinator.project_manager.reset_analysis_data.assert_called_once()


def test_register_project_outputs(coordinator):
    coordinator.register_project_outputs(
        video_path="video.mp4",
        results_dir="res",
        trajectory_path="traj.parquet",
        summary_parquet="sum.parquet",
        summary_excel="sum.xlsx",
        report_path="rep.docx",
    )

    coordinator.project_manager.register_processing_outputs.assert_called_once()


def test_are_project_overrides_active(coordinator):
    coordinator._model_override_service.are_project_overrides_active.return_value = True
    assert coordinator.are_project_overrides_active() is True


def test_has_project_override_settings(coordinator):
    coordinator._model_override_service.has_project_override_settings.return_value = True
    assert coordinator.has_project_override_settings() is True


def test_copy_global_model_settings_to_project(coordinator):
    coordinator._model_override_service.copy_global_model_settings_to_project.return_value = (
        "test",
        True,
    )

    result = coordinator.copy_global_model_settings_to_project(lambda: {}, lambda: "test")

    assert result == ("test", True)


def test_resolve_project_model_settings(coordinator):
    coordinator._model_override_service.resolve_project_model_settings.return_value = ("test", True)

    result = coordinator.resolve_project_model_settings()

    assert result == ("test", True)


def test_save_current_calibration_to_project(coordinator):
    coordinator._model_override_service.save_current_calibration_to_project.return_value = (
        "test",
        True,
    )

    result = coordinator.save_current_calibration_to_project(lambda: "test", lambda: True)

    assert result == ("test", True)


def test_apply_project_model_overrides(coordinator):
    coordinator._model_override_service.apply_project_model_overrides.return_value = ("test", True)

    result = coordinator.apply_project_model_overrides(
        active_weight_setter=lambda x: None,
        use_openvino_setter=lambda x: None,
    )

    assert result == ("test", True)


def test_save_project_model_overrides(coordinator):
    coordinator._model_override_service.save_project_model_overrides.return_value = ("test", True)

    result = coordinator.save_project_model_overrides("test", True, lambda: "test", lambda: True)

    assert result == ("test", True)


def test_save_project_model_slot_overrides(coordinator):
    coordinator._model_override_service.save_project_model_slot_overrides.return_value = (
        "test",
        True,
    )

    result = coordinator.save_project_model_slot_overrides({}, True)

    assert result == ("test", True)


def test_get_calibration_scope_info(coordinator):
    coordinator._calibration_coordinator.get_calibration_scope_info.return_value = {"scope": "test"}

    result = coordinator.get_calibration_scope_info()

    assert result == {"scope": "test"}


def test_build_calibration_context(coordinator):
    coordinator._calibration_coordinator.build_calibration_context.return_value = (
        MagicMock(),
        (1.0, 1.0),
    )

    cal, ratio = coordinator.build_calibration_context([], {})

    assert cal is not None
    assert ratio == (1.0, 1.0)


def test_handle_aquarium_config_updated(coordinator):
    mock_zone_manager = MagicMock()
    mock_zone_data = MagicMock()
    mock_aquarium = MagicMock()
    mock_zone_data.get_aquarium.return_value = mock_aquarium
    mock_zone_manager.get_multi_aquarium_zone_data.return_value = mock_zone_data

    coordinator.register_event_handlers(zone_manager=mock_zone_manager)

    payload = {
        "aquarium_id": 1,
        "config": {"group": "g1", "subject_id": "s1", "day": "d1"},
        "video_path": "video.mp4",
    }

    coordinator._handle_aquarium_config_updated(payload)

    assert mock_aquarium.group == "g1"
    assert mock_aquarium.subject_id == "s1"
    assert mock_aquarium.day == "d1"
    mock_zone_manager.save_multi_aquarium_zone_data.assert_called_once()


def test_stop_live_session_if_active_no_service(coordinator):
    coordinator.live_camera_service = None
    coordinator._stop_live_session_if_active()


def test_stop_live_session_if_active_not_callable(coordinator):
    coordinator.live_camera_service.is_session_active = "not_callable"
    coordinator._stop_live_session_if_active()


def test_stop_live_session_if_active_true(coordinator):
    coordinator.live_camera_service.is_session_active.return_value = True
    coordinator._stop_live_session_if_active()
    coordinator.live_camera_service.stop_session.assert_called_once()


def test_close_project_stops_live_session(coordinator):
    coordinator.live_camera_service.is_session_active.return_value = True
    coordinator.close_project()
    coordinator.live_camera_service.stop_session.assert_called_once()


def test_handle_aquarium_config_updated_missing_data(coordinator):
    coordinator._handle_aquarium_config_updated({})


def test_handle_aquarium_config_updated_no_zone_manager(coordinator):
    coordinator._zone_manager = None
    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {}, "video_path": "path"}
    )


def test_handle_aquarium_config_updated_no_zone_data(coordinator):
    mock_zm = MagicMock()
    mock_zm.get_multi_aquarium_zone_data.return_value = None
    coordinator._zone_manager = mock_zm
    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "g1"}, "video_path": "path"}
    )


def test_handle_aquarium_config_updated_no_aquarium(coordinator):
    mock_zm = MagicMock()
    mock_zd = MagicMock()
    mock_zd.get_aquarium.return_value = None
    mock_zm.get_multi_aquarium_zone_data.return_value = mock_zd
    coordinator._zone_manager = mock_zm
    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "g1"}, "video_path": "path"}
    )


def test_handle_aquarium_config_updated_dict_config(coordinator):
    mock_zm = MagicMock()
    mock_zd = MagicMock()
    mock_aq = MagicMock()
    mock_aq.group = "old"
    mock_aq.subject_id = "old"
    mock_aq.day = "old"
    mock_zd.get_aquarium.return_value = mock_aq
    mock_zm.get_multi_aquarium_zone_data.return_value = mock_zd
    coordinator._zone_manager = mock_zm

    coordinator._handle_aquarium_config_updated(
        {
            "aquarium_id": 1,
            "config": {"group": "new_g", "subject_id": "new_s", "day": "new_d"},
            "video_path": "path",
        }
    )

    assert mock_aq.group == "new_g"
    assert mock_aq.subject_id == "new_s"
    assert mock_aq.day == "new_d"
    mock_zm.save_multi_aquarium_zone_data.assert_called_once_with("path", mock_zd)


def test_handle_aquarium_config_updated_exception(coordinator):
    mock_zm = MagicMock()
    mock_zm.get_multi_aquarium_zone_data.side_effect = Exception("test error")
    coordinator._zone_manager = mock_zm
    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "g1"}, "video_path": "path"}
    )


def test_create_project_default_callbacks_failure(coordinator):
    # test create project without passing explicit callbacks to trigger default callbacks
    coordinator.project_workflow_service.create_project.return_value = {
        "success": False,
        "error_message": "test error default",
    }
    result = coordinator.create_project(use_openvino=True, active_weight="test_weight")
    assert result is False


def test_create_project_default_callbacks_success(coordinator):
    # test create project with success using default callbacks
    coordinator.project_workflow_service.create_project.return_value = {
        "success": True,
        "error_message": None,
        "animal_method": "zebrafish",
        "wizard_metadata": {"some_data": 1},
    }
    # Mock detector service to return True
    coordinator.detector_service.initialize_detector.return_value = (True, "")

    # Needs a mock for get_detector_state if used
    mock_ds = MagicMock()
    mock_ds.use_openvino = False
    mock_ds.active_weight_name = None
    coordinator.state_manager.get_detector_state.return_value = mock_ds

    result = coordinator.create_project(use_openvino=True, active_weight="test_weight")
    assert result is True
    # Ensure apply_wizard_overrides is called via default callback
    # Event bus is used to show UI updates
    assert coordinator.event_bus.publish.call_count > 0


def test_default_setup_detector(coordinator):
    mock_ds = MagicMock()
    mock_ds.use_openvino = True
    mock_ds.active_weight_name = "test_weight"
    coordinator.state_manager.get_detector_state.return_value = mock_ds

    # Mock openvino ready
    coordinator.detector_service.model_service.is_openvino_ready.return_value = False

    coordinator._default_setup_detector("zebrafish")
    # Should fallback to openvino=False
    coordinator.state_manager.update_detector_state.assert_called_with(
        source="project_lifecycle_coordinator.openvino_fallback",
        use_openvino=False,
    )
