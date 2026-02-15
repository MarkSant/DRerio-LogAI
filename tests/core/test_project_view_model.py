"""Tests for ProjectViewModel."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from zebtrack.core.viewmodels.project_view_model import ProjectViewModel


@pytest.fixture
def view_model():
    """Create a ProjectViewModel with dependencies."""
    project_manager = Mock()
    project_manager.project_path = None
    project_manager.project_data = {"name": "Test Project"}

    state_manager = Mock()
    state_manager.get_state.return_value = {
        "active_weight_name": "weights.pt",
        "use_openvino": True,
    }

    project_lifecycle_coordinator = Mock()
    project_workflow_service = Mock()
    batch_configuration_service = Mock()
    batch_configuration_service.apply_settings.return_value = ["ok"]

    settings_obj = SimpleNamespace(
        weights=SimpleNamespace(det_filename="default.pt"),
        model_selection=SimpleNamespace(use_openvino=False),
    )

    dependencies = SimpleNamespace(
        project_manager=project_manager,
        state_manager=state_manager,
        project_lifecycle_coordinator=project_lifecycle_coordinator,
        project_workflow_service=project_workflow_service,
        settings_obj=settings_obj,
    )
    bootstrap_result = SimpleNamespace(batch_configuration_service=batch_configuration_service)
    event_bus = Mock()

    return ProjectViewModel(
        cast(Any, dependencies),
        cast(Any, bootstrap_result),
        event_bus,
    )


def test_create_project_workflow_delegates(view_model):
    view_model.project_lifecycle_coordinator.create_project.return_value = "ok"

    result = view_model.create_project_workflow(name="Project")

    assert result == "ok"
    view_model.project_lifecycle_coordinator.create_project.assert_called_once_with(name="Project")


def test_open_and_close_project_workflow(view_model):
    view_model.project_lifecycle_coordinator.open_project.return_value = True
    view_model.project_lifecycle_coordinator.close_project.return_value = True

    assert view_model.open_project_workflow("/project") is True
    assert view_model.close_project() is True


def test_on_video_selected_sets_active_zone_video(view_model):
    view_model.on_video_selected("/video.mp4")

    view_model.project_manager.set_active_zone_video.assert_called_once_with("/video.mp4")


def test_handle_delete_project_asset_delegates(view_model):
    view_model.handle_delete_project_asset("/video.mp4", "arena", delete_source=True)

    view_model.project_lifecycle_coordinator.delete_project_asset.assert_called_once_with(
        "/video.mp4", "arena", delete_source=True
    )


def test_can_remove_project_asset_without_coordinator(view_model):
    view_model.project_lifecycle_coordinator = None

    allowed, reason = view_model.can_remove_project_asset("/video.mp4", "arena")

    assert allowed is False
    assert reason == "ProjectLifecycleCoordinator not available"


def test_apply_project_settings_to_batch(view_model):
    result = view_model.apply_project_settings_to_batch(["v1"])

    assert result == ["ok"]
    view_model.batch_configuration_service.apply_settings.assert_called_once_with(["v1"])


def test_resolve_project_model_settings_no_coordinator(view_model):
    view_model.project_lifecycle_coordinator = None

    assert view_model.resolve_project_model_settings({"x": 1}) == (None, False)


def test_save_project_model_overrides_passes_callbacks(view_model):
    view_model.save_project_model_overrides("weights.pt", True)

    args = view_model.project_lifecycle_coordinator.save_project_model_overrides.call_args[0]
    assert args[0] == "weights.pt"
    assert args[1] is True
    get_active_weight_name = args[2]
    get_use_openvino = args[3]
    assert get_active_weight_name() == "weights.pt"
    assert get_use_openvino() is True


def test_has_project_override_settings(view_model):
    view_model.project_lifecycle_coordinator.has_project_override_settings.return_value = True

    assert view_model.has_project_override_settings() is True


def test_handle_calibration_copy_to_project(view_model):
    view_model.handle_calibration_copy_to_project()

    args = view_model.project_lifecycle_coordinator.copy_global_model_settings_to_project.call_args
    get_global_defaults = args.kwargs["get_global_defaults"]
    get_active_weight_name = args.kwargs["get_active_weight_name"]

    assert get_global_defaults() == {"active_weight": "default.pt", "use_openvino": False}
    assert get_active_weight_name() == "weights.pt"


def test_handle_calibration_save_to_project(view_model):
    view_model.handle_calibration_save_to_project()

    args = view_model.project_lifecycle_coordinator.save_current_calibration_to_project.call_args
    get_active_weight_name = args.kwargs["get_active_weight_name"]
    get_use_openvino = args.kwargs["get_use_openvino"]

    assert get_active_weight_name() == "weights.pt"
    assert get_use_openvino() is True


def test_get_calibration_scope_info_defaults(view_model):
    view_model.project_lifecycle_coordinator = None

    info = view_model.get_calibration_scope_info()

    assert info["scope"] == "global"
    assert info["project_loaded"] is False


def test_get_calibration_scope_info_delegates(view_model):
    view_model.project_lifecycle_coordinator.get_calibration_scope_info.return_value = {
        "scope": "project",
        "label": "Projeto",
        "detail": "ok",
        "project_loaded": True,
    }

    info = view_model.get_calibration_scope_info()

    assert info["scope"] == "project"
    view_model.project_lifecycle_coordinator.get_calibration_scope_info.assert_called_once()


def test_project_data_property(view_model):
    assert view_model.project_data == {"name": "Test Project"}

    view_model.project_manager = None
    assert view_model.project_data == {}
