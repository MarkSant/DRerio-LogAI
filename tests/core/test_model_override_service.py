"""Tests for ModelOverrideService."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.core.services.model_override_service import ModelOverrideService


def _build_service(*, project_path: str | None, overrides: dict[str, Any]) -> ModelOverrideService:
    project_manager = Mock()
    project_manager.project_path = project_path
    project_manager.project_data = {"model_overrides": overrides}

    return ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )


def test_has_project_override_settings_ignores_empty_slot_weights() -> None:
    service = _build_service(
        project_path="/tmp/project",
        overrides={
            "active_weight": None,
            "use_openvino": None,
            "device": "AUTO",
            "slot_weights": {},
        },
    )

    assert service.has_project_override_settings() is False


def test_has_project_override_settings_detects_slot_weight_override() -> None:
    service = _build_service(
        project_path="/tmp/project",
        overrides={
            "active_weight": None,
            "use_openvino": None,
            "device": "AUTO",
            "slot_weights": {"seg:zebrafish": "project_seg.pt"},
        },
    )

    assert service.has_project_override_settings() is True


def test_has_project_override_settings_detects_explicit_openvino_override() -> None:
    service = _build_service(
        project_path="/tmp/project",
        overrides={
            "active_weight": None,
            "use_openvino": False,
            "device": "AUTO",
            "slot_weights": {},
        },
    )

    assert service.has_project_override_settings() is True


def test_restore_global_model_defaults_reapplies_saved_runtime_defaults() -> None:
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {"model_overrides": {"slot_weights": {}}}

    state_manager = Mock()
    workflow_service = Mock()
    workflow_service._global_model_defaults = {
        "active_weight": "global.pt",
        "use_openvino": True,
    }
    workflow_service.model_service = SimpleNamespace(weight_manager=Mock())

    service = ModelOverrideService(
        state_manager=cast(Any, state_manager),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, workflow_service),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )
    service._using_project_overrides = True

    service.restore_global_model_defaults()

    workflow_service.set_global_model_defaults.assert_called_once_with("global.pt", True)
    state_manager.update_detector_state.assert_called_once_with(
        source="model_override_service.restore_global_model_defaults",
        active_weight_name="global.pt",
        use_openvino=True,
    )
    workflow_service.model_service.weight_manager.clear_runtime_slot_overrides.assert_called_once()
    assert service.are_project_overrides_active() is False


# === Bug C: copy_global_model_settings_to_project must propagate to runtime ==


def test_copy_global_model_settings_forwards_real_setters_and_runtime_callback() -> None:
    """Regression: the old code chamed
    ``save_project_model_slot_overrides`` with ``lambda _: None`` for
    both setters and never invoked the runtime apply. Result: disk
    updated, detector untouched. The fix routes real setters and an
    ``apply_runtime_callback`` through to the workflow service.
    """
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {"model_overrides": {"slot_weights": {}}}

    workflow_service = Mock()
    workflow_service.get_global_project_slot_weights.return_value = {
        "det:zebrafish": "global_det.pt"
    }
    workflow_service.save_project_model_slot_overrides.return_value = (
        "global_det.pt",
        True,
    )

    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, workflow_service),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=Mock(),
    )

    get_global_defaults = Mock(
        return_value={"active_weight": "global_det.pt", "use_openvino": True}
    )
    get_active_weight = Mock(return_value="global_det.pt")
    refresh = Mock()
    set_weight = Mock()
    set_openvino = Mock()
    apply_runtime = Mock()

    result = service.copy_global_model_settings_to_project(
        get_global_defaults,
        get_active_weight,
        refresh,
        active_weight_setter=set_weight,
        use_openvino_setter=set_openvino,
        apply_runtime_callback=apply_runtime,
    )

    assert result == ("global_det.pt", True)
    # Setters reais devem chegar ate o workflow service (nao podem ser
    # substituidos por lambdas no-op).
    workflow_service.save_project_model_slot_overrides.assert_called_once()
    _, kwargs = workflow_service.save_project_model_slot_overrides.call_args
    assert kwargs["active_weight_setter"] is set_weight
    assert kwargs["use_openvino_setter"] is set_openvino
    # Runtime callback deve ser chamado com os valores resolvidos.
    apply_runtime.assert_called_once_with("global_det.pt", True)
    refresh.assert_called_once()


def test_copy_global_model_settings_skips_runtime_callback_when_omitted() -> None:
    """Backwards-compat: callers that do not pass an
    ``apply_runtime_callback`` keep the old behavior (disk only)."""
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {"model_overrides": {"slot_weights": {}}}

    workflow_service = Mock()
    workflow_service.get_global_project_slot_weights.return_value = {
        "det:zebrafish": "global_det.pt"
    }
    workflow_service.save_project_model_slot_overrides.return_value = (
        "global_det.pt",
        False,
    )

    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, workflow_service),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=Mock(),
    )

    service.copy_global_model_settings_to_project(
        Mock(return_value={"active_weight": "global_det.pt", "use_openvino": False}),
        Mock(return_value="global_det.pt"),
    )

    workflow_service.save_project_model_slot_overrides.assert_called_once()


def test_save_project_model_slot_overrides_passes_setters_to_apply() -> None:
    """Phase-level regression: ``save_project_model_slot_overrides`` itself
    used to hardcode no-op lambdas when calling
    ``apply_project_model_overrides``. Now it propagates whatever setters
    its caller supplied (and only falls back to no-op when omitted).
    """
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService

    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {
        "model_overrides": {
            "active_weight": None,
            "use_openvino": None,
            "device": "AUTO",
            "slot_weights": {},
        }
    }

    service = ProjectWorkflowService(
        project_manager=cast(Any, project_manager),
        model_service=cast(Any, Mock()),
        state_manager=cast(Any, Mock()),
        ui_coordinator=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace(openvino=SimpleNamespace(device="AUTO"))),
    )

    seen_weights: list[str | None] = []
    seen_openvino: list[bool] = []

    def fake_apply(*, overrides, active_weight_setter, use_openvino_setter):
        active_weight_setter("resolved_weight.pt")
        use_openvino_setter(True)
        return "resolved_weight.pt", True

    service.apply_project_model_overrides = fake_apply  # type: ignore[assignment]

    service.save_project_model_slot_overrides(
        {"det:zebrafish": "resolved_weight.pt"},
        True,
        active_weight_setter=lambda w: seen_weights.append(w),
        use_openvino_setter=lambda v: seen_openvino.append(v),
    )

    assert seen_weights == ["resolved_weight.pt"]
    assert seen_openvino == [True]
