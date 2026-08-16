"""
Extended unit tests for MainViewModel in core/main_view_model.py.
"""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock

import pytest

from zebtrack.core.application_bootstrapper import (
    BootstrapResult,
    HardwareBootstrap,
    RuntimeBootstrap,
)
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.main_view_model import MainViewModel
from zebtrack.settings import load_settings
from zebtrack.ui.event_bus_v2 import EventBusV2


class TestMainViewModelExtended:
    """Test MainViewModel initialization, sub-viewmodel composition, and delegation."""

    @pytest.fixture
    def mock_deps(self) -> MagicMock:
        deps = MagicMock(spec=MainViewModelDependencies)
        deps.root = MagicMock()
        deps.settings_obj = load_settings()
        deps.test_sync_event = None
        deps.state_manager = MagicMock()
        deps.project_manager = MagicMock()
        deps.weight_manager = MagicMock()
        deps.model_service = MagicMock()
        deps.detector_service = MagicMock()
        deps.event_bus = EventBusV2()
        deps.ui_coordinator = MagicMock()
        deps.progress_coordinator = MagicMock()
        deps.model_coordinator = MagicMock()
        deps.recording_session_coordinator = MagicMock()
        deps.live_camera_session_coordinator = MagicMock()
        deps.calibration_coordinator = MagicMock()
        deps.live_calibration_coordinator = MagicMock()
        deps.live_batch_coordinator = MagicMock()
        deps.detector_setup_coordinator = MagicMock()
        deps.video_processing_coordinator = MagicMock()
        deps.sequential_processing_coordinator = MagicMock()
        deps.multi_aquarium_coordinator = MagicMock()
        deps.report_generation_coordinator = MagicMock()
        deps.project_lifecycle_coordinator = MagicMock()
        deps.trajectory_data_service = MagicMock()
        deps.video_metadata_service = MagicMock()
        deps.video_processing_service = MagicMock()
        deps.project_workflow_service = MagicMock()
        deps.recording_service = MagicMock()
        deps.live_camera_service = MagicMock()
        deps.dialog_coordinator = MagicMock()
        deps.analysis_service = MagicMock()
        return deps

    @pytest.fixture
    def mock_bootstrap_result(self) -> BootstrapResult:
        hw = HardwareBootstrap(
            active_weight_name="yolo11n.pt",
            use_openvino=False,
            hardware_summary={"cpu": "Intel"},
            recommended_backend="cpu",
            recorder=MagicMock(),
            arduino_manager=None,
        )
        rt = RuntimeBootstrap(
            frame_queue=queue.Queue(),
            video_queue=queue.Queue(),
            program_exit_event=threading.Event(),
            cancel_event=threading.Event(),
        )
        return BootstrapResult(
            project_service=MagicMock(),
            analysis_service=MagicMock(),
            video_classification_service=MagicMock(),
            video_selection_service=MagicMock(),
            video_validation_service=MagicMock(),
            batch_configuration_service=MagicMock(),
            dialog_coordinator=MagicMock(),
            event_dispatcher=MagicMock(),
            hardware=hw,
            runtime=rt,
            view=MagicMock(),
            ui_state_controller=MagicMock(),
            project_workflow_adapter=MagicMock(),
        )

    def test_main_view_model_sub_viewmodels_instantiation(
        self, mock_deps: MagicMock, mock_bootstrap_result: BootstrapResult
    ):
        vm = MainViewModel(dependencies=mock_deps, bootstrap_result=mock_bootstrap_result)

        assert vm.project_vm is not None
        assert vm.analysis_vm is not None
        assert vm.hardware_vm is not None
        assert vm.view is mock_bootstrap_result.view
        assert vm.project_service is mock_bootstrap_result.project_service
        assert vm.analysis_service is mock_bootstrap_result.analysis_service
        assert vm.active_weight_name == "yolo11n.pt"

    def test_main_view_model_run_and_shutdown(
        self, mock_deps: MagicMock, mock_bootstrap_result: BootstrapResult
    ):
        vm = MainViewModel(dependencies=mock_deps, bootstrap_result=mock_bootstrap_result)

        # Mock root.mainloop to return immediately
        mock_deps.root.mainloop = MagicMock()
        vm.run()
        mock_deps.root.mainloop.assert_called_once()
