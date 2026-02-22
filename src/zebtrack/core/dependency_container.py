from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

from zebtrack.analysis.analysis_service import AnalysisService

# Phase 3 → Phase 4: Super Coordinators
# ProcessingCoordinator decomposed into 5 sub-coordinators (Phase 4)
# SessionCoordinator decomposed into 3 sub-coordinators (Phase 4.7)
# HardwareCoordinator decomposed into 2 sub-coordinators (Phase 4.9)
from zebtrack.coordinators.detector_setup_coordinator import DetectorSetupCoordinator
from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator
from zebtrack.coordinators.model_diagnostics_coordinator import ModelDiagnosticsCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording.live_camera_service import LiveCameraService
from zebtrack.core.recording.recording_service import RecordingService
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_scheduler import UIScheduler
from zebtrack.core.video.video_processing_service import VideoProcessingService
from zebtrack.settings import Settings
from zebtrack.ui.event_bus_v2 import EventBusV2
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter


@dataclass
class MainViewModelDependencies:
    """Encapsulates all dependencies required by MainViewModel.

    This reduces the number of arguments in MainViewModel.__init__ and
    makes dependency injection more structured.

    Phase 3 Update:
        - Added 4 super coordinators (ProjectLifecycleCoordinator, HardwareCoordinator,
          ProcessingCoordinator, SessionCoordinator)
    Phase 4.9 Update:
        - HardwareCoordinator decomposed into DetectorSetupCoordinator +
          ModelDiagnosticsCoordinator
        - Removed LEGACY detector_coordinator field
    """

    # Core infrastructure
    root: Any  # tk.Tk
    settings_obj: Settings
    event_bus: EventBusV2 | None
    state_manager: StateManager
    ui_coordinator: UIScheduler  # Renamed from UICoordinator to avoid collision

    # Domain managers
    project_manager: ProjectManager
    project_workflow_service: ProjectWorkflowService
    weight_manager: WeightManager
    model_service: ModelService

    # Domain services
    detector_service: DetectorService
    video_processing_service: VideoProcessingService
    analysis_service: AnalysisService | None = None
    recording_service: RecordingService | None = None
    live_camera_service: LiveCameraService | None = None
    ui_state_controller: UIStateController | None = None

    # Phase 3 → Phase 4: Super Coordinators
    # processing_coordinator now is VideoProcessingCoordinator (Phase 4 decomposition)
    # session_coordinator decomposed into 3 sub-coordinators (Phase 4.7)
    # hardware_coordinator decomposed into 2 sub-coordinators (Phase 4.9)
    project_lifecycle_coordinator: ProjectLifecycleCoordinator | None = None
    detector_setup_coordinator: DetectorSetupCoordinator | None = None
    model_diagnostics_coordinator: ModelDiagnosticsCoordinator | None = None
    processing_coordinator: VideoProcessingCoordinator | None = None
    recording_session_coordinator: RecordingSessionCoordinator | None = None
    live_camera_session_coordinator: LiveCameraSessionCoordinator | None = None
    live_calibration_coordinator: LiveCalibrationCoordinator | None = None
    project_workflow_adapter: ProjectWorkflowAdapter | None = None
    live_batch_coordinator: LiveBatchCoordinator | None = None  # v2.3.0

    # Runtime State
    cancel_event: Any = None

    # Testing
    test_sync_event: Any = None
