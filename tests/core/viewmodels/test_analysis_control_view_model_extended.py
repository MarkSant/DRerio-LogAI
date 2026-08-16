"""
Extended unit tests for AnalysisControlViewModel.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.ui.event_bus_v2 import UIEvents


class TestAnalysisControlViewModelExtended:
    """Test AnalysisControlViewModel workflow start/stop and validation."""

    @pytest.fixture
    def mock_vm(self):
        deps = MagicMock()
        deps.settings_obj.model_selection.animal_method = "det"
        boot = MagicMock()
        boot.hardware.recorder = MagicMock()
        boot.analysis_service = MagicMock()
        boot.ui_state_controller = MagicMock()
        boot.runtime.cancel_event = MagicMock()
        event_bus = MagicMock()
        return AnalysisControlViewModel(
            dependencies=deps,
            bootstrap_result=boot,
            event_bus=event_bus,
        )

    def test_is_processing_property(self, mock_vm: AnalysisControlViewModel):
        proc_state = MagicMock()
        proc_state.is_processing = True
        mock_vm.state_manager.get_processing_state.return_value = proc_state
        assert mock_vm.is_processing is True

    def test_start_project_processing_workflow(self, mock_vm: AnalysisControlViewModel):
        mock_vm.start_project_processing_workflow()
        mock_vm.processing_coordinator.start_project_processing_workflow.assert_called_once()

    def test_start_single_video_workflow_validation_error(
        self, mock_vm: AnalysisControlViewModel, tmp_path: Path
    ):
        # 'det' method with 2 animals -> invalid
        video = tmp_path / "video.mp4"
        config = {"animal_method": "det", "animals_per_aquarium": 2}
        mock_vm.start_single_video_workflow(video, config)

        mock_vm.ui_event_bus.publish.assert_called_once()
        event = mock_vm.ui_event_bus.publish.call_args[0][0]
        assert event.type == UIEvents.SHOW_ERROR
        assert "Invalid Configuration" in event.data.title
