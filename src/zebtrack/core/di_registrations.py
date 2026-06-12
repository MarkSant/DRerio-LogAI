"""DI container registrations for ZebTrack-AI.

This module centralizes dependency wiring for the composition root, keeping
__main__.py focused on startup orchestration.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import punq  # type: ignore[import-untyped]
import structlog

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
from zebtrack.core.main_view_model import MainViewModel
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.project.project_service import ProjectService
from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording.live_camera_service import LiveCameraService
from zebtrack.core.recording.recording_service import RecordingService
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.model_override_service import ModelOverrideService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.trajectory_data_service import TrajectoryDataService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_scheduler import UIScheduler
from zebtrack.core.video.video_classification_service import VideoClassificationService
from zebtrack.core.video.video_metadata_service import VideoMetadataService
from zebtrack.core.video.video_processing_service import VideoProcessingService
from zebtrack.core.video.video_selection_service import VideoSelectionService
from zebtrack.core.video.video_validation_service import VideoValidationService
from zebtrack.io.recorder_factory import RecorderFactory
from zebtrack.settings import Settings
from zebtrack.ui.event_bus_v2 import EventBusV2
from zebtrack.ui.gui import ApplicationGUI
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter
from zebtrack.utils.video_frame_extractor import VideoFrameExtractor


@dataclass(frozen=True)
class ContainerContext:
    """Shared context required to build the DI container."""

    root: Any
    settings_obj: Settings
    event_bus: EventBusV2
    state_manager: StateManager
    ui_coordinator: UIScheduler
    recorder_factory: RecorderFactory
    cancel_event: threading.Event
    controller_ref: LazyRef


T = TypeVar("T")

log = structlog.get_logger()


def _resolve(container: punq.Container, cls: type[T]) -> T:
    return cast(T, container.resolve(cls))


def build_container(context: ContainerContext) -> punq.Container:
    """Create and configure the DI container with all registrations."""
    container = punq.Container()
    settings_obj = context.settings_obj

    container.register(Settings, instance=settings_obj)
    container.register(EventBusV2, instance=context.event_bus)
    container.register(StateManager, instance=context.state_manager)
    container.register(UIScheduler, instance=context.ui_coordinator)
    container.register(RecorderFactory, instance=context.recorder_factory)
    container.register(LazyRef, instance=context.controller_ref)

    container.register(
        WeightManager,
        factory=lambda: WeightManager(settings_obj=settings_obj),
        scope=punq.Scope.singleton,
    )
    container.register(
        ModelService,
        factory=lambda: ModelService(weight_manager=_resolve(container, WeightManager)),
        scope=punq.Scope.singleton,
    )
    container.register(
        ProjectManager,
        factory=lambda: ProjectManager(
            state_manager=_resolve(container, StateManager),
            settings_obj=settings_obj,
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        ProjectWorkflowService,
        factory=lambda: ProjectWorkflowService(
            project_manager=_resolve(container, ProjectManager),
            model_service=_resolve(container, ModelService),
            state_manager=_resolve(container, StateManager),
            ui_coordinator=_resolve(container, UIScheduler),
            settings_obj=settings_obj,
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        DetectorService,
        factory=lambda: DetectorService(
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            weight_manager=_resolve(container, WeightManager),
            model_service=_resolve(container, ModelService),
            settings_obj=settings_obj,
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        VideoProcessingService,
        factory=lambda: VideoProcessingService(
            project_manager=_resolve(container, ProjectManager),
            state_manager=_resolve(container, StateManager),
            ui_coordinator=_resolve(container, UIScheduler),
            ui_event_bus=_resolve(container, EventBusV2),
            cancel_event=context.cancel_event,
            settings_obj=settings_obj,
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        AnalysisService,
        factory=lambda: AnalysisService(settings_obj=settings_obj),
        scope=punq.Scope.singleton,
    )
    container.register(
        RecordingService,
        factory=lambda: RecordingService(
            controller=cast(Any, _resolve(container, LazyRef)),
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            root=context.root,
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        LiveCameraService,
        factory=lambda: LiveCameraService(
            controller=cast(Any, _resolve(container, LazyRef)),
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            recording_service=_resolve(container, RecordingService),
            detector_service=_resolve(container, DetectorService),
            settings_obj=settings_obj,
            recorder=context.recorder_factory.get_recorder(),
            event_bus=_resolve(container, EventBusV2),
            root=context.root,
            project_workflow_service=_resolve(container, ProjectWorkflowService),
        ),
        scope=punq.Scope.singleton,
    )

    container.register(
        ProjectService,
        factory=lambda: ProjectService(),
        scope=punq.Scope.singleton,
    )
    container.register(
        ProjectWorkflowAdapter,
        factory=lambda: ProjectWorkflowAdapter(
            project_workflow_service=_resolve(container, ProjectWorkflowService),
            project_manager=_resolve(container, ProjectManager),
            detector_service=_resolve(container, DetectorService),
            state_manager=_resolve(container, StateManager),
            ui_event_bus=_resolve(container, EventBusV2),
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        ModelOverrideService,
        factory=lambda: ModelOverrideService(
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            project_workflow_service=_resolve(container, ProjectWorkflowService),
            settings_obj=settings_obj,
            event_bus=_resolve(container, EventBusV2),
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        CalibrationCoordinator,
        factory=lambda: CalibrationCoordinator(
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            model_override_service=_resolve(container, ModelOverrideService),
            event_bus=_resolve(container, EventBusV2),
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        ProjectLifecycleCoordinator,
        factory=lambda: ProjectLifecycleCoordinator(
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
            project_workflow_service=_resolve(container, ProjectWorkflowService),
            project_workflow_adapter=_resolve(container, ProjectWorkflowAdapter),
            settings_obj=settings_obj,
            event_bus=_resolve(container, EventBusV2),
            detector_service=_resolve(container, DetectorService),
            model_override_service=_resolve(container, ModelOverrideService),
            calibration_coordinator=_resolve(container, CalibrationCoordinator),
            live_camera_service=_resolve(container, LiveCameraService),
        ),
        scope=punq.Scope.singleton,
    )
    container.register(
        DetectorSetupCoordinator,
        factory=lambda: DetectorSetupCoordinator(
            state_manager=_resolve(container, StateManager),
            detector_service=_resolve(container, DetectorService),
            model_service=_resolve(container, ModelService),
            weight_manager=_resolve(container, WeightManager),
            event_bus=_resolve(container, EventBusV2),
        ),
        scope=punq.Scope.singleton,
    )

    container.register(
        ApplicationGUI,
        factory=lambda: _build_application_gui(context, container),
        scope=punq.Scope.singleton,
    )

    container.register(
        DialogCoordinator,
        factory=lambda: DialogCoordinator(
            ui_coordinator=_resolve(container, UIScheduler),
            event_bus=_resolve(container, EventBusV2),
            state_manager=_resolve(container, StateManager),
            project_manager=_resolve(container, ProjectManager),
        ),
        scope=punq.Scope.singleton,
    )

    container.register(
        UIStateController,
        factory=lambda: UIStateController(
            root=context.root,
            ui_event_bus=_resolve(container, EventBusV2),
            state_manager=_resolve(container, StateManager),
            ui_coordinator=_resolve(container, UIScheduler),
            project_manager=_resolve(container, ProjectManager),
            weight_manager=_resolve(container, WeightManager),
            detector_service=_resolve(container, DetectorService),
            model_service=_resolve(container, ModelService),
            settings=settings_obj,
            detector_coordinator=_resolve(container, DetectorSetupCoordinator),
            project_workflow_service=_resolve(container, ProjectWorkflowService),
            main_view_model=_resolve(container, LazyRef),
            view=_resolve(container, ApplicationGUI),
        ),
        scope=punq.Scope.singleton,
    )

    container.register(
        ModelDiagnosticsCoordinator,
        factory=lambda: ModelDiagnosticsCoordinator(
            state_manager=_resolve(container, StateManager),
            weight_manager=_resolve(container, WeightManager),
            event_bus=_resolve(container, EventBusV2),
            cancel_event=context.cancel_event,
            root=context.root,
            view=_resolve(container, ApplicationGUI),
        ),
        scope=punq.Scope.singleton,
    )

    _register_processing_cluster(container, context)
    _register_session_cluster(container, context)

    container.register(
        MainViewModelDependencies,
        factory=lambda: MainViewModelDependencies(
            root=context.root,
            settings_obj=settings_obj,
            event_bus=_resolve(container, EventBusV2),
            state_manager=_resolve(container, StateManager),
            ui_coordinator=_resolve(container, UIScheduler),
            project_manager=_resolve(container, ProjectManager),
            project_workflow_service=_resolve(container, ProjectWorkflowService),
            project_workflow_adapter=_resolve(container, ProjectWorkflowAdapter),
            weight_manager=_resolve(container, WeightManager),
            model_service=_resolve(container, ModelService),
            detector_service=_resolve(container, DetectorService),
            video_processing_service=_resolve(container, VideoProcessingService),
            analysis_service=_resolve(container, AnalysisService),
            recording_service=_resolve(container, RecordingService),
            live_camera_service=_resolve(container, LiveCameraService),
            ui_state_controller=_resolve(container, UIStateController),
            project_lifecycle_coordinator=_resolve(container, ProjectLifecycleCoordinator),
            detector_setup_coordinator=_resolve(container, DetectorSetupCoordinator),
            model_diagnostics_coordinator=_resolve(container, ModelDiagnosticsCoordinator),
            processing_coordinator=_resolve(container, VideoProcessingCoordinator),
            recording_session_coordinator=_resolve(container, RecordingSessionCoordinator),
            live_camera_session_coordinator=_resolve(container, LiveCameraSessionCoordinator),
            live_calibration_coordinator=_resolve(container, LiveCalibrationCoordinator),
            live_batch_coordinator=_resolve(container, LiveBatchCoordinator),
            controller_ref=_resolve(container, LazyRef),
            cancel_event=context.cancel_event,
            dialog_coordinator=_resolve(container, DialogCoordinator),
        ),
        scope=punq.Scope.singleton,
    )

    container.register(
        ApplicationBootstrapper,
        factory=lambda: ApplicationBootstrapper(
            _resolve(container, MainViewModelDependencies),
            view=_resolve(container, ApplicationGUI),
        ),
        scope=punq.Scope.singleton,
    )

    return container


def resolve_main_view_model(container: punq.Container) -> MainViewModel:
    """Resolve the fully wired MainViewModel with bootstrap initialization."""
    controller_ref = _resolve(container, LazyRef)
    dependencies = _resolve(container, MainViewModelDependencies)

    # Fail-fast: surface missing coordinator wiring before the app starts
    missing = dependencies.validate()
    if missing:
        log.warning(
            "di.dependencies.missing_coordinators",
            missing=missing,
            msg="Some coordinator slots were not wired during DI registration",
        )

    bootstrapper = _resolve(container, ApplicationBootstrapper)
    bootstrap_result = bootstrapper.initialize(controller_ref)

    controller = MainViewModel(dependencies, bootstrap_result)
    controller_ref.set(controller)
    return controller


def _build_application_gui(
    context: ContainerContext,
    container: punq.Container,
) -> ApplicationGUI:
    ui_features = getattr(context.settings_obj, "ui_features", None)
    has_event_bus = _resolve(container, EventBusV2) is not None
    has_feature_flag = ui_features and getattr(ui_features, "enable_event_queue", False)
    use_event_bus = bool(has_event_bus or has_feature_flag)

    return ApplicationGUI(
        context.root,
        _resolve(container, LazyRef),
        event_bus=_resolve(container, EventBusV2) if use_event_bus else None,
        settings_obj=context.settings_obj,
        project_manager=_resolve(container, ProjectManager),
        state_manager=_resolve(container, StateManager),
    )


def _register_processing_cluster(container: punq.Container, context: ContainerContext) -> None:
    view = _resolve(container, ApplicationGUI)
    state_manager = _resolve(container, StateManager)
    project_manager = _resolve(container, ProjectManager)
    detector_service = _resolve(container, DetectorService)
    weight_manager = _resolve(container, WeightManager)
    ui_coordinator = _resolve(container, UIScheduler)
    event_bus = _resolve(container, EventBusV2)

    video_selection_service = VideoSelectionService()
    video_validation_service = VideoValidationService()
    video_classification_service = VideoClassificationService()
    video_metadata_service = VideoMetadataService()
    trajectory_data_service = TrajectoryDataService()
    video_frame_extractor = VideoFrameExtractor()

    container.register(VideoSelectionService, instance=video_selection_service)
    container.register(VideoValidationService, instance=video_validation_service)
    container.register(VideoClassificationService, instance=video_classification_service)
    container.register(VideoMetadataService, instance=video_metadata_service)
    container.register(TrajectoryDataService, instance=trajectory_data_service)
    container.register(VideoFrameExtractor, instance=video_frame_extractor)

    progress_tracking_coordinator = ProgressTrackingCoordinator(
        state_manager=state_manager,
        settings_obj=context.settings_obj,
        ui_coordinator=ui_coordinator,
        cancel_event=context.cancel_event,
        event_bus=event_bus,
        view=view,
        root=context.root,
    )
    multi_aquarium_coordinator = MultiAquariumCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=context.settings_obj,
        ui_coordinator=ui_coordinator,
        ui_state_controller=_resolve(container, UIStateController),
        cancel_event=context.cancel_event,
        video_classification_service=video_classification_service,
        weight_manager=weight_manager,
        event_bus=event_bus,
        view=view,
        root=context.root,
        detector=None,
    )
    report_generation_coordinator = ReportGenerationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        settings_obj=context.settings_obj,
        analysis_service=_resolve(container, AnalysisService),
        event_bus=event_bus,
        video_metadata_service=video_metadata_service,
        trajectory_data_service=trajectory_data_service,
        video_frame_extractor=video_frame_extractor,
    )
    sequential_processing_coordinator = SequentialProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=context.settings_obj,
        ui_coordinator=ui_coordinator,
        cancel_event=context.cancel_event,
        recorder_factory=context.recorder_factory,
        event_bus=event_bus,
        view=view,
        root=context.root,
    )
    processing_coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        weight_manager=weight_manager,
        settings_obj=context.settings_obj,
        ui_coordinator=ui_coordinator,
        ui_state_controller=_resolve(container, UIStateController),
        cancel_event=context.cancel_event,
        video_selection_service=video_selection_service,
        video_validation_service=video_validation_service,
        video_classification_service=video_classification_service,
        recorder_factory=context.recorder_factory,
        event_bus=event_bus,
        dialog_coordinator=_resolve(container, DialogCoordinator),
        video_metadata_service=video_metadata_service,
        view=view,
        root=context.root,
        detector=None,
    )

    processing_coordinator._progress_coordinator = progress_tracking_coordinator
    processing_coordinator._multi_aquarium_coordinator = multi_aquarium_coordinator
    processing_coordinator._sequential_coordinator = sequential_processing_coordinator
    processing_coordinator._report_coordinator = report_generation_coordinator

    progress_tracking_coordinator._video_processing_coordinator = processing_coordinator
    sequential_processing_coordinator._video_processing_coordinator = processing_coordinator
    sequential_processing_coordinator._report_coordinator = report_generation_coordinator
    sequential_processing_coordinator._progress_coordinator = progress_tracking_coordinator
    report_generation_coordinator._progress_coordinator = progress_tracking_coordinator

    container.register(ProgressTrackingCoordinator, instance=progress_tracking_coordinator)
    container.register(MultiAquariumCoordinator, instance=multi_aquarium_coordinator)
    container.register(ReportGenerationCoordinator, instance=report_generation_coordinator)
    container.register(SequentialProcessingCoordinator, instance=sequential_processing_coordinator)
    container.register(VideoProcessingCoordinator, instance=processing_coordinator)


def _register_session_cluster(container: punq.Container, context: ContainerContext) -> None:
    view = _resolve(container, ApplicationGUI)
    state_manager = _resolve(container, StateManager)
    project_manager = _resolve(container, ProjectManager)
    detector_service = _resolve(container, DetectorService)
    weight_manager = _resolve(container, WeightManager)
    event_bus = _resolve(container, EventBusV2)

    live_batch_coordinator = LiveBatchCoordinator(
        project_manager=project_manager,
        analysis_service=_resolve(container, AnalysisService),
        state_manager=state_manager,
        settings_obj=context.settings_obj,
        event_bus=event_bus if context.settings_obj.ui_features.enable_event_queue else None,
    )
    live_calibration_coordinator = LiveCalibrationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        weight_manager=weight_manager,
        settings_obj=context.settings_obj,
        event_bus=event_bus,
        root=context.root,
        view=view,
    )
    recording_session_coordinator = RecordingSessionCoordinator(
        state_manager=state_manager,
        recording_service=_resolve(container, RecordingService),
        live_camera_service=_resolve(container, LiveCameraService),
        project_manager=project_manager,
        settings_obj=context.settings_obj,
        live_calibration_coordinator=live_calibration_coordinator,
        event_bus=event_bus,
        arduino_manager=None,
        root=context.root,
        view=view,
    )
    live_camera_session_coordinator = LiveCameraSessionCoordinator(
        state_manager=state_manager,
        live_camera_service=_resolve(container, LiveCameraService),
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=context.settings_obj,
        live_calibration_coordinator=live_calibration_coordinator,
        event_bus=event_bus,
        live_batch_coordinator=live_batch_coordinator,
        root=context.root,
        view=view,
    )

    container.register(LiveBatchCoordinator, instance=live_batch_coordinator)
    container.register(LiveCalibrationCoordinator, instance=live_calibration_coordinator)
    container.register(RecordingSessionCoordinator, instance=recording_session_coordinator)
    container.register(LiveCameraSessionCoordinator, instance=live_camera_session_coordinator)
