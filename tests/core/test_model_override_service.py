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
