"""
Extended unit tests for AnalysisControlViewModel.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.ui.event_bus_v2 import UIEvents


def _make_vm() -> AnalysisControlViewModel:
    deps = MagicMock()
    deps.settings_obj.model_selection.animal_method = "det"
    boot = MagicMock()
    boot.hardware.recorder = MagicMock()
    boot.analysis_service = MagicMock()
    boot.ui_state_controller = MagicMock()
    boot.runtime.cancel_event = MagicMock()
    return AnalysisControlViewModel(
        dependencies=deps,
        bootstrap_result=boot,
        event_bus=MagicMock(),
    )


class TestAnalysisControlViewModelExtended:
    """Test AnalysisControlViewModel workflow start/stop and validation."""

    def test_is_processing_property(self):
        vm = _make_vm()
        proc_state = MagicMock()
        proc_state.is_processing = True
        vm.state_manager.get_processing_state.return_value = proc_state  # type: ignore[union-attr,attr-defined]
        assert vm.is_processing is True

    def test_start_project_processing_workflow(self):
        vm = _make_vm()
        vm.start_project_processing_workflow()
        vm.processing_coordinator.start_project_processing_workflow.assert_called_once()  # type: ignore[union-attr]

    def test_start_single_video_workflow_validation_error(self, tmp_path: Path):
        vm = _make_vm()
        video = tmp_path / "video.mp4"
        config = {"animal_method": "det", "animals_per_aquarium": 2}
        vm.start_single_video_workflow(video, config)

        vm.ui_event_bus.publish.assert_called_once()
        event = vm.ui_event_bus.publish.call_args[0][0]
        assert event.type == UIEvents.SHOW_ERROR
        assert "Invalid Configuration" in event.data.title
