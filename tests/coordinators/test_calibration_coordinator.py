from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.calibration_coordinator import CalibrationCoordinator


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_project_manager():
    pm = MagicMock()
    pm.project_path = "test/path"
    pm.get_project_name.return_value = "Test Project"
    pm.project_data = {}
    return pm


@pytest.fixture
def mock_model_override_service():
    mos = MagicMock()
    mos.has_project_override_settings.return_value = False
    mos._using_project_overrides = False
    mos._global_model_defaults = {}
    return mos


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def coordinator(
    mock_state_manager,
    mock_project_manager,
    mock_model_override_service,
    mock_event_bus,
):
    return CalibrationCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        model_override_service=mock_model_override_service,
        event_bus=mock_event_bus,
    )


def test_get_calibration_scope_info_global(coordinator):
    # Setup global scope
    coordinator.project_manager.project_path = None

    info = coordinator.get_calibration_scope_info()

    assert info["scope"] == "global"
    assert not info["project_loaded"]
    assert "Global Configuration" in info["label"]
    assert not info["is_single_video_mode"]


def test_get_calibration_scope_info_project_with_overrides(coordinator):
    # Setup project scope with overrides
    coordinator.model_override_service.has_project_override_settings.return_value = True
    coordinator.model_override_service._using_project_overrides = True

    info = coordinator.get_calibration_scope_info()

    assert info["scope"] == "project"
    assert info["project_loaded"]
    assert info["project_name"] == "Test Project"
    assert "Project (Test Project)" in info["label"]
    assert info["overrides_active"]
    assert not info["inheriting_globals"]


def test_get_calibration_scope_info_project_inheriting(coordinator):
    # Setup project scope inheriting global
    coordinator.model_override_service.has_project_override_settings.return_value = False
    coordinator.model_override_service._using_project_overrides = False

    info = coordinator.get_calibration_scope_info()

    assert info["scope"] == "global"
    assert info["project_loaded"]
    assert "Global Configuration" in info["label"]
    assert not info["overrides_active"]
    assert info["inheriting_globals"]


def test_get_calibration_scope_info_single_video(coordinator):
    gui_mock = MagicMock()
    gui_mock.pending_single_video_path = "some/path.mp4"

    info = coordinator.get_calibration_scope_info(gui_instance=gui_mock)

    assert info["is_single_video_mode"]


@patch("zebtrack.coordinators.calibration_coordinator.Calibration")
def test_build_calibration_context_with_data(mock_calibration_class, coordinator):
    mock_cal_instance = MagicMock()
    mock_cal_instance.pixel_per_cm_ratio = 5.0
    mock_calibration_class.return_value = mock_cal_instance

    arena_polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
    calibration_data = {"aquarium_width_cm": 10.0, "aquarium_height_cm": 10.0}

    cal, ratio = coordinator.build_calibration_context(arena_polygon, calibration_data)

    assert cal is mock_cal_instance
    assert ratio == 5.0
    mock_calibration_class.assert_called_once()


@patch("zebtrack.coordinators.calibration_coordinator.Calibration")
def test_build_calibration_context_from_project_data(mock_calibration_class, coordinator):
    mock_cal_instance = MagicMock()
    mock_cal_instance.pixel_per_cm_ratio = 5.0
    mock_calibration_class.return_value = mock_cal_instance

    arena_polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
    coordinator.project_manager.project_data = {
        "calibration": {"aquarium_width_cm": 10.0, "aquarium_height_cm": 10.0}
    }

    cal, ratio = coordinator.build_calibration_context(arena_polygon, None)

    assert cal is mock_cal_instance
    assert ratio == 5.0
    mock_calibration_class.assert_called_once()


def test_build_calibration_context_empty(coordinator):
    cal, ratio = coordinator.build_calibration_context(None, None)
    assert cal is None
    assert ratio is None


def test_global_calibration_session(coordinator):
    active_weight_mock = MagicMock(return_value="test_weight")
    use_openvino_mock = MagicMock(return_value=True)

    coordinator.model_override_service._using_project_overrides = True

    with coordinator.global_calibration_session(active_weight_mock, use_openvino_mock):
        assert not coordinator.model_override_service._using_project_overrides

    assert coordinator.model_override_service._using_project_overrides
    assert (
        coordinator.model_override_service._global_model_defaults["active_weight"] == "test_weight"
    )
    assert coordinator.model_override_service._global_model_defaults["use_openvino"] is True


def test_project_calibration_session(coordinator):
    coordinator.model_override_service._using_project_overrides = False
    coordinator.model_override_service.has_project_override_settings.return_value = True

    with coordinator.project_calibration_session():
        assert coordinator.model_override_service._using_project_overrides

    assert coordinator.model_override_service._using_project_overrides


def test_project_calibration_session_revert(coordinator):
    coordinator.model_override_service._using_project_overrides = False
    coordinator.model_override_service.has_project_override_settings.return_value = False

    with coordinator.project_calibration_session():
        assert coordinator.model_override_service._using_project_overrides

    assert not coordinator.model_override_service._using_project_overrides
