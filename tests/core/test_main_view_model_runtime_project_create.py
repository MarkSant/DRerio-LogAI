"""Regression tests for PROJECT_CREATE payload handling in MainViewModelRuntime."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.core.viewmodels.main_view_model_runtime import MainViewModelRuntime
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents


def _build_vm_stub() -> SimpleNamespace:
    project_vm = Mock()
    return SimpleNamespace(project_vm=project_vm)


def test_project_create_merges_nested_wizard_data() -> None:
    """Nested wizard_data must be merged before invoking project workflow."""
    vm = _build_vm_stub()
    runtime = MainViewModelRuntime(cast(Any, vm))

    payload = payloads.ProjectCreatePayload(
        project_path="/top/path",
        project_name="TopName",
        project_type="experimental",
        wizard_data={
            "project_name": "NestedName",
            "video_count": 3,
            "scanned_videos": [{"path": "/videos/a.mp4"}],
        },
    )

    runtime.handle_event(UIEvents.PROJECT_CREATE, payload)

    vm.project_vm.create_project_workflow.assert_called_once()
    kwargs = vm.project_vm.create_project_workflow.call_args.kwargs
    assert kwargs["project_name"] == "NestedName"
    assert kwargs["project_path"] == "/top/path"
    assert kwargs["project_type"] == "experimental"
    assert kwargs["video_count"] == 3
    assert kwargs["scanned_videos"][0]["path"] == "/videos/a.mp4"


def test_project_create_accepts_flat_payload_without_wizard_data() -> None:
    """Flat payload must keep working when wizard_data is missing."""
    vm = _build_vm_stub()
    runtime = MainViewModelRuntime(cast(Any, vm))

    payload = payloads.ProjectCreatePayload(
        project_path="/flat/path",
        project_name="FlatProject",
        project_type="live",
        wizard_data=None,
    )

    runtime.handle_event(UIEvents.PROJECT_CREATE, payload)

    vm.project_vm.create_project_workflow.assert_called_once_with(
        project_path="/flat/path",
        project_name="FlatProject",
        project_type="live",
    )
