"""
Extended unit tests for DI container registrations in core/di_registrations.py.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.coordinators.calibration_coordinator import CalibrationCoordinator
from zebtrack.coordinators.detector_setup_coordinator import DetectorSetupCoordinator
from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator
from zebtrack.coordinators.model_diagnostics_coordinator import ModelDiagnosticsCoordinator
from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.sequential_processing_coordinator import SequentialProcessingCoordinator
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.application_bootstrapper import ApplicationBootstrapper
from zebtrack.core.dependency_container import LazyRef, MainViewModelDependencies
from zebtrack.core.di_registrations import (
    ContainerContext,
    _resolve,
    build_container,
)
from zebtrack.core.project.project_service import ProjectService
from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.core.services.model_override_service import ModelOverrideService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.trajectory_data_service import TrajectoryDataService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_scheduler import UIScheduler
from zebtrack.core.video.video_classification_service import VideoClassificationService
from zebtrack.core.video.video_metadata_service import VideoMetadataService
from zebtrack.core.video.video_selection_service import VideoSelectionService
from zebtrack.core.video.video_validation_service import VideoValidationService
from zebtrack.io.recorder_factory import RecorderFactory
from zebtrack.settings import load_settings
from zebtrack.ui.event_bus_v2 import EventBusV2
from zebtrack.ui.gui import ApplicationGUI
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter


class TestDiRegistrationsExtended:
    """Test ContainerContext and build_container registrations."""

    @pytest.fixture
    def container_context(self) -> ContainerContext:
        settings_obj = load_settings()
        event_bus = EventBusV2()
        state_manager = StateManager()
        ui_scheduler = UIScheduler(event_bus=event_bus)
        recorder_factory = RecorderFactory(settings_obj=settings_obj)
        cancel_event = threading.Event()
        controller_ref = LazyRef()

        return ContainerContext(
            root=MagicMock(),
            settings_obj=settings_obj,
            event_bus=event_bus,
            state_manager=state_manager,
            ui_coordinator=ui_scheduler,
            recorder_factory=recorder_factory,
            cancel_event=cancel_event,
            controller_ref=controller_ref,
        )

    def test_container_context_fields(self, container_context: ContainerContext):
        assert container_context.settings_obj is not None
        assert container_context.event_bus is not None
        assert container_context.state_manager is not None
        assert container_context.ui_coordinator is not None
        assert container_context.recorder_factory is not None
        assert container_context.cancel_event is not None
        assert container_context.controller_ref is not None

    def test_build_container_resolves_core_services(self, container_context: ContainerContext):
        with patch("zebtrack.core.di_registrations._build_application_gui") as mock_gui:
            mock_gui.return_value = MagicMock(spec=ApplicationGUI)
            container = build_container(container_context)

            # Core services
            assert _resolve(container, WeightManager) is not None
            assert _resolve(container, ModelService) is not None
            assert _resolve(container, ModelOverrideService) is not None
            assert _resolve(container, TrajectoryDataService) is not None
            assert _resolve(container, VideoMetadataService) is not None
            assert _resolve(container, VideoSelectionService) is not None
            assert _resolve(container, VideoValidationService) is not None
            assert _resolve(container, VideoClassificationService) is not None
            assert _resolve(container, ProjectWorkflowService) is not None
            assert _resolve(container, ProjectService) is not None
            assert _resolve(container, AnalysisService) is not None

    def test_build_container_resolves_coordinators(self, container_context: ContainerContext):
        with patch("zebtrack.core.di_registrations._build_application_gui") as mock_gui:
            mock_gui.return_value = MagicMock(spec=ApplicationGUI)
            container = build_container(container_context)

            # Coordinators
            assert _resolve(container, DialogCoordinator) is not None
            assert _resolve(container, UIStateController) is not None
            assert _resolve(container, ProgressTrackingCoordinator) is not None
            assert _resolve(container, ModelDiagnosticsCoordinator) is not None
            assert _resolve(container, RecordingSessionCoordinator) is not None
            assert _resolve(container, LiveCameraSessionCoordinator) is not None
            assert _resolve(container, CalibrationCoordinator) is not None
            assert _resolve(container, LiveCalibrationCoordinator) is not None
            assert _resolve(container, LiveBatchCoordinator) is not None
            assert _resolve(container, DetectorSetupCoordinator) is not None
            assert _resolve(container, VideoProcessingCoordinator) is not None
            assert _resolve(container, SequentialProcessingCoordinator) is not None
            assert _resolve(container, MultiAquariumCoordinator) is not None
            assert _resolve(container, ReportGenerationCoordinator) is not None
            assert _resolve(container, ProjectLifecycleCoordinator) is not None

    def test_build_container_resolves_bootstrapper_and_dependencies(
        self, container_context: ContainerContext
    ):
        with patch("zebtrack.core.di_registrations._build_application_gui") as mock_gui:
            mock_gui.return_value = MagicMock(spec=ApplicationGUI)
            container = build_container(container_context)

            deps = _resolve(container, MainViewModelDependencies)
            assert deps is not None
            assert isinstance(deps, MainViewModelDependencies)

            adapter = _resolve(container, ProjectWorkflowAdapter)
            assert adapter is not None

            bootstrapper = _resolve(container, ApplicationBootstrapper)
            assert bootstrapper is not None
