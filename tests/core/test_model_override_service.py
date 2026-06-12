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


# === Guard clauses sem projeto aberto ===


def test_are_project_overrides_active_default_false() -> None:
    service = _build_service(project_path=None, overrides={"slot_weights": {}})
    assert service.are_project_overrides_active() is False


def test_copy_global_returns_none_without_project() -> None:
    project_manager = Mock()
    project_manager.project_path = None
    project_manager.project_data = {}
    event_bus = Mock()
    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=event_bus,
    )

    result = service.copy_global_model_settings_to_project(
        get_global_defaults=lambda: {},
        get_active_weight_name=lambda: None,
    )

    assert result is None
    event_bus.publish.assert_called()  # aviso "Nenhum Projeto"


def test_save_current_calibration_returns_none_without_project() -> None:
    service = _build_service(project_path=None, overrides={"slot_weights": {}})
    result = service.save_current_calibration_to_project(
        get_active_weight_name=lambda: "w",
        get_use_openvino=lambda: False,
    )
    assert result is None


def test_save_project_model_overrides_returns_current_without_project() -> None:
    # Mock local do workflow para assertar sem esbarrar na tipagem do atributo.
    workflow = Mock()
    project_manager = Mock()
    project_manager.project_path = None
    project_manager.project_data = {"model_overrides": {"slot_weights": {}}}
    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, workflow),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )

    result = service.save_project_model_overrides(
        active_weight_override="w",
        use_openvino_override=True,
        get_active_weight_name=lambda: "atual",
        get_use_openvino=lambda: True,
    )

    assert result == ("atual", True)
    workflow.save_project_model_slot_overrides.assert_not_called()


# === Persistência em project_data ===


def test_ensure_overrides_record_creates_when_missing() -> None:
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {}
    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )

    rec = service._ensure_project_overrides_record()

    assert "slot_weights" in rec
    assert project_manager.project_data["model_overrides"] is rec


def test_ensure_overrides_record_adds_slot_weights_key() -> None:
    service = _build_service(project_path="/tmp/project", overrides={"active_weight": "x"})
    rec = service._ensure_project_overrides_record()
    assert rec["slot_weights"] == {}


def test_persist_writes_weight_and_openvino_and_saves() -> None:
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {}
    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )

    overrides = service._persist_project_model_settings("best.pt", True)

    assert overrides["active_weight"] == "best.pt"
    assert overrides["use_openvino"] is True
    assert project_manager.project_data["active_weight"] == "best.pt"
    project_manager.save_project.assert_called_once()


def test_persist_without_path_does_not_save() -> None:
    project_manager = Mock()
    project_manager.project_path = None
    project_manager.project_data = {}
    service = ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, Mock()),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )

    service._persist_project_model_settings("w", False)

    project_manager.save_project.assert_not_called()


# === Delegações ao workflow service ===


def _build_service_with_workflow(workflow: Mock) -> ModelOverrideService:
    """Variante de _build_service que recebe o mock do workflow para asserções."""
    project_manager = Mock()
    project_manager.project_path = "/tmp/project"
    project_manager.project_data = {"model_overrides": {"slot_weights": {}}}
    return ModelOverrideService(
        state_manager=cast(Any, Mock()),
        project_manager=cast(Any, project_manager),
        project_workflow_service=cast(Any, workflow),
        settings_obj=cast(Any, SimpleNamespace()),
        event_bus=None,
    )


def test_resolve_delegates_to_workflow() -> None:
    workflow = Mock()
    workflow.resolve_project_model_settings.return_value = ("w", True)
    service = _build_service_with_workflow(workflow)

    assert service.resolve_project_model_settings({"a": 1}) == ("w", True)
    workflow.resolve_project_model_settings.assert_called_once_with({"a": 1})


def test_apply_delegates_to_workflow() -> None:
    workflow = Mock()
    workflow.apply_project_model_overrides.return_value = ("w", False)
    service = _build_service_with_workflow(workflow)

    result = service.apply_project_model_overrides(
        overrides={"x": 1},
        active_weight_setter=lambda w: None,
        use_openvino_setter=lambda v: None,
    )
    assert result == ("w", False)
