"""Regression tests for MODEL_* payload handling in MainViewModelRuntime."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.core.viewmodels.main_view_model_runtime import MainViewModelRuntime
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents


def _build_vm_stub() -> SimpleNamespace:
    return SimpleNamespace(
        hardware_vm=Mock(),
        project_vm=Mock(),
        analysis_vm=Mock(),
    )


def test_model_set_weight_accepts_legacy_weight_name_field() -> None:
    """Legacy payloads using `weight_name` must still resolve to set_active_weight."""
    vm = _build_vm_stub()
    runtime = MainViewModelRuntime(cast(Any, vm))
    dialog = object()

    payload = payloads.ModelSetWeightPayload(weight_name="legacy.pt", dialog=dialog)

    runtime.handle_event(UIEvents.MODEL_SET_WEIGHT, payload)

    vm.hardware_vm.set_active_weight.assert_called_once_with(
        "legacy.pt",
        dialog=dialog,
    )


def test_model_set_weight_prefers_name_field_when_present() -> None:
    """Current payloads should keep using `name` even if legacy fields exist."""
    vm = _build_vm_stub()
    runtime = MainViewModelRuntime(cast(Any, vm))

    payload = payloads.ModelSetWeightPayload(
        name="current.pt",
        weight_name="legacy.pt",
        dialog=None,
    )

    runtime.handle_event(UIEvents.MODEL_SET_WEIGHT, payload)

    vm.hardware_vm.set_active_weight.assert_called_once_with(
        "current.pt",
        dialog=None,
    )
