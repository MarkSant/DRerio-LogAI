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

    # Espelha o shape real de Settings: pesos aninhados por perspectiva e o
    # helper get_default_det_filename (não existe weights.det_filename plano).
    settings_obj = SimpleNamespace(
        weights=SimpleNamespace(
            lateral=SimpleNamespace(det_filename="default.pt", seg_filename="seg.pt"),
            top_down=SimpleNamespace(det_filename="default_td.pt", seg_filename="seg_td.pt"),
        ),
        model_selection=SimpleNamespace(use_openvino=False),
        behavioral_analysis=SimpleNamespace(aquarium_perspective="lateral"),
        get_default_det_filename=lambda: "default.pt",
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


def test_save_project_model_slot_overrides_delegates(view_model):
    view_model.save_project_model_slot_overrides({"seg:zebrafish": "weights.pt"}, True)

    view_model.project_lifecycle_coordinator.save_project_model_slot_overrides.assert_called_once_with(
        {"seg:zebrafish": "weights.pt"},
        True,
    )


def test_has_project_override_settings(view_model):
    view_model.project_lifecycle_coordinator.has_project_override_settings.return_value = True

    assert view_model.has_project_override_settings() is True


def test_handle_calibration_copy_to_project(view_model):
    view_model.project_lifecycle_coordinator.copy_global_model_settings_to_project.return_value = (
        "default.pt",
        False,
    )

    result = view_model.handle_calibration_copy_to_project()

    args = view_model.project_lifecycle_coordinator.copy_global_model_settings_to_project.call_args
    get_global_defaults = args.kwargs["get_global_defaults"]
    get_active_weight_name = args.kwargs["get_active_weight_name"]

    assert result == ("default.pt", False)
    assert get_global_defaults() == {"active_weight": "default.pt", "use_openvino": False}
    assert get_active_weight_name() == "weights.pt"


def test_handle_calibration_copy_to_project_path(view_model):
    coordinator = view_model.project_lifecycle_coordinator
    coordinator.copy_global_model_settings_to_project_path.return_value = ("default.pt", True)

    result = view_model.handle_calibration_copy_to_project_path("C:/projetos/alvo")

    assert result == ("default.pt", True)
    args = coordinator.copy_global_model_settings_to_project_path.call_args
    assert args.args[0] == "C:/projetos/alvo"
    get_global_defaults = args.kwargs["get_global_defaults"]
    assert get_global_defaults() == {"active_weight": "default.pt", "use_openvino": False}


def test_handle_calibration_copy_to_project_returns_none_without_coordinator(view_model):
    view_model.project_lifecycle_coordinator = None

    assert view_model.handle_calibration_copy_to_project() is None
    assert view_model.handle_calibration_copy_to_project_path("C:/qualquer") is None


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


# ---------------------------------------------------------------------------
# Absent-coordinator fallbacks: every call degrades to a typed neutral value
# ---------------------------------------------------------------------------


@pytest.fixture
def orphan_view_model(view_model):
    """The same view model with no ProjectLifecycleCoordinator wired."""
    view_model.project_lifecycle_coordinator = None
    return view_model


def test_lifecycle_calls_return_none_without_a_coordinator(orphan_view_model):
    vm = orphan_view_model

    assert vm.create_project_workflow(name="P") is None
    assert vm.open_project_workflow("/p") is None
    assert vm.close_project() is None
    assert vm.resolve_project_model_settings({"a": 1}) == (None, False)


def test_destructive_calls_fail_closed_without_a_coordinator(orphan_view_model):
    vm = orphan_view_model

    assert vm.handle_delete_hierarchy_node("group", group_id="g") == (0, 0)
    assert vm.handle_delete_aquarium("/v.mp4", 1) is False
    assert vm.handle_clear_aquarium_subject("/v.mp4", 1) is False
    assert vm.handle_reset_analysis_data("/v.mp4") is False
    assert vm.has_project_override_settings() is False
    vm.handle_delete_project_asset("/v.mp4", "trajectory")  # must not raise


def test_asset_removal_check_explains_why_it_is_refused_without_a_coordinator(orphan_view_model):
    assert orphan_view_model.can_remove_project_asset("/v.mp4", "trajectory") == (
        False,
        "ProjectLifecycleCoordinator not available",
    )


def test_model_override_saves_and_calibration_copies_are_noops_without_a_coordinator(
    orphan_view_model,
):
    vm = orphan_view_model

    vm.save_project_model_overrides("w.pt", True)
    vm.save_project_model_slot_overrides({"seg:aquarium": "w.pt"}, False)
    assert vm.handle_calibration_copy_to_project() is None
    assert vm.handle_calibration_copy_to_project_path("/proj") is None


def test_calibration_scope_info_reports_a_global_scope_without_a_coordinator(orphan_view_model):
    assert orphan_view_model.get_calibration_scope_info() == {
        "scope": "global",
        "label": "Global",
        "detail": "N/A",
        "project_loaded": False,
    }


def test_video_selection_without_a_project_manager_is_ignored(view_model):
    view_model.project_manager = None

    view_model.on_video_selected("/v.mp4")  # must not raise


def test_project_data_is_empty_without_a_project_manager(view_model):
    assert view_model.project_data == {"name": "Test Project"}

    view_model.project_manager = None

    assert view_model.project_data == {}


# ---------------------------------------------------------------------------
# Forwarding with exact arguments
# ---------------------------------------------------------------------------


def test_deletion_calls_forward_every_option(view_model):
    coordinator = view_model.project_lifecycle_coordinator
    coordinator.delete_hierarchy_node.return_value = (2, 5)
    coordinator.delete_aquarium_scope.return_value = True
    coordinator.clear_aquarium_subject.return_value = True
    coordinator.reset_analysis_data.return_value = True

    assert view_model.handle_delete_hierarchy_node(
        "subject", group_id="g", day_id="d", subject_id="s", delete_files=False
    ) == (2, 5)
    assert view_model.handle_delete_aquarium("/v.mp4", 2, delete_files=False, delete_zone=False)
    assert view_model.handle_clear_aquarium_subject(
        "/v.mp4", 2, delete_analysis_data=False, delete_files=False
    )
    assert view_model.handle_reset_analysis_data("/v.mp4", aquarium_id=3, delete_files=False)
    view_model.handle_delete_project_asset("/v.mp4", "summary", delete_source=True)

    coordinator.delete_hierarchy_node.assert_called_once_with(
        "subject", group_id="g", day_id="d", subject_id="s", delete_files=False
    )
    coordinator.delete_aquarium_scope.assert_called_once_with(
        "/v.mp4", 2, delete_files=False, delete_zone=False
    )
    coordinator.clear_aquarium_subject.assert_called_once_with(
        "/v.mp4", 2, delete_analysis_data=False, delete_files=False
    )
    coordinator.reset_analysis_data.assert_called_once_with(
        "/v.mp4", aquarium_id=3, delete_files=False
    )
    coordinator.delete_project_asset.assert_called_once_with(
        "/v.mp4", "summary", delete_source=True
    )


def test_deletion_defaults_delete_files_and_keep_the_source(view_model):
    coordinator = view_model.project_lifecycle_coordinator

    view_model.handle_delete_hierarchy_node("group", group_id="g")
    view_model.handle_delete_aquarium("/v.mp4", 0)
    view_model.handle_reset_analysis_data("/v.mp4")
    view_model.handle_delete_project_asset("/v.mp4", "summary")

    coordinator.delete_hierarchy_node.assert_called_once_with(
        "group", group_id="g", day_id=None, subject_id=None, delete_files=True
    )
    coordinator.delete_aquarium_scope.assert_called_once_with(
        "/v.mp4", 0, delete_files=True, delete_zone=True
    )
    coordinator.reset_analysis_data.assert_called_once_with(
        "/v.mp4", aquarium_id=None, delete_files=True
    )
    coordinator.delete_project_asset.assert_called_once_with(
        "/v.mp4", "summary", delete_source=False
    )


def test_can_remove_project_asset_returns_the_coordinators_verdict(view_model):
    view_model.project_lifecycle_coordinator.can_remove_project_asset.return_value = (
        False,
        "in use",
    )

    assert view_model.can_remove_project_asset("/v.mp4", "zones") == (False, "in use")


def test_resolve_project_model_settings_returns_the_coordinators_answer(view_model):
    view_model.project_lifecycle_coordinator.resolve_project_model_settings.return_value = (
        "w.pt",
        True,
    )

    assert view_model.resolve_project_model_settings({"k": 1}) == ("w.pt", True)
    view_model.project_lifecycle_coordinator.resolve_project_model_settings.assert_called_once_with(
        {"k": 1}
    )


def test_slot_overrides_are_forwarded_verbatim(view_model):
    view_model.save_project_model_slot_overrides({"seg:aquarium": "a.pt"}, None)

    view_model.project_lifecycle_coordinator.save_project_model_slot_overrides.assert_called_once_with(
        {"seg:aquarium": "a.pt"}, None
    )


def test_has_project_override_settings_returns_the_coordinators_answer(view_model):
    view_model.project_lifecycle_coordinator.has_project_override_settings.return_value = True

    assert view_model.has_project_override_settings() is True


# ---------------------------------------------------------------------------
# State-backed callbacks handed to the coordinator
# ---------------------------------------------------------------------------


def _saved_callbacks(view_model):
    call = view_model.project_lifecycle_coordinator.save_project_model_overrides.call_args
    return call.args


def test_save_model_overrides_hands_the_coordinator_live_state_readers(view_model):
    view_model.save_project_model_overrides("w.pt", False)

    active, use_ov, get_weight, get_openvino = _saved_callbacks(view_model)
    assert (active, use_ov) == ("w.pt", False)
    assert get_weight() == "weights.pt"
    assert get_openvino() is True


def test_state_readers_see_state_changes_made_after_the_call(view_model):
    view_model.save_project_model_overrides(None, None)
    _active, _use, get_weight, get_openvino = _saved_callbacks(view_model)

    view_model.state_manager.get_state.return_value = {"active_weight_name": "new.pt"}

    assert get_weight() == "new.pt"
    assert get_openvino() is False  # absent key defaults to False


def test_state_readers_are_neutral_without_a_state_manager(view_model):
    view_model.save_project_model_overrides(None, None)
    _active, _use, get_weight, get_openvino = _saved_callbacks(view_model)

    view_model.state_manager = None

    assert get_weight() is None
    assert get_openvino() is False


def test_calibration_scope_info_returns_the_coordinators_dict(view_model):
    info = {"scope": "project", "label": "P", "detail": "x", "project_loaded": True}
    view_model.project_lifecycle_coordinator.get_calibration_scope_info.return_value = info

    assert view_model.get_calibration_scope_info() is info
    # The scope does not depend on the active weight: no callback is handed over
    # (#726 -- the coordinator used to accept one and never call it).
    view_model.project_lifecycle_coordinator.get_calibration_scope_info.assert_called_once_with()


def test_copy_to_project_builds_global_defaults_from_settings(view_model):
    coordinator = view_model.project_lifecycle_coordinator
    coordinator.copy_global_model_settings_to_project.return_value = ("default.pt", False)

    assert view_model.handle_calibration_copy_to_project() == ("default.pt", False)

    kwargs = coordinator.copy_global_model_settings_to_project.call_args.kwargs
    assert kwargs["get_global_defaults"]() == {"active_weight": "default.pt", "use_openvino": False}
    assert kwargs["get_active_weight_name"]() == "weights.pt"


def test_copy_to_project_global_defaults_without_settings_are_empty(view_model):
    coordinator = view_model.project_lifecycle_coordinator
    view_model.handle_calibration_copy_to_project()
    kwargs = coordinator.copy_global_model_settings_to_project.call_args.kwargs

    view_model.settings = None
    view_model.state_manager = None

    assert kwargs["get_global_defaults"]() == {"active_weight": None, "use_openvino": False}
    assert kwargs["get_active_weight_name"]() is None


def test_copy_to_project_reports_failure_as_none(view_model):
    view_model.project_lifecycle_coordinator.copy_global_model_settings_to_project.return_value = (
        None
    )

    assert view_model.handle_calibration_copy_to_project() is None


def test_copy_to_project_path_targets_the_given_directory(view_model):
    coordinator = view_model.project_lifecycle_coordinator
    coordinator.copy_global_model_settings_to_project_path.return_value = ("default.pt", False)

    assert view_model.handle_calibration_copy_to_project_path("/proj") == ("default.pt", False)

    call = coordinator.copy_global_model_settings_to_project_path.call_args
    assert call.args == ("/proj",)
    assert call.kwargs["get_global_defaults"]() == {
        "active_weight": "default.pt",
        "use_openvino": False,
    }
    assert call.kwargs["get_active_weight_name"]() == "weights.pt"


def test_apply_project_settings_to_batch_returns_the_services_result(view_model):
    assert view_model.apply_project_settings_to_batch([{"p": 1}]) == ["ok"]
    view_model.batch_configuration_service.apply_settings.assert_called_once_with([{"p": 1}])
