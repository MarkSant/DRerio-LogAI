from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

from zebtrack.analysis.analysis_service import AnalysisService

# Phase 3 → Phase 4: Super Coordinators
# ProcessingCoordinator decomposed into 5 sub-coordinators (Phase 4)
# SessionCoordinator decomposed into 3 sub-coordinators (Phase 4.7)
from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.live_camera_service import LiveCameraService
from zebtrack.core.model_service import ModelService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_scheduler import UIScheduler
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.weight_manager import WeightManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter


@dataclass
class MainViewModelDependencies:
    """Encapsulates all dependencies required by MainViewModel.

    This reduces the number of arguments in MainViewModel.__init__ and
    makes dependency injection more structured.

    Phase 3 Update:
        - Added 4 super coordinators (ProjectLifecycleCoordinator, HardwareCoordinator,
          ProcessingCoordinator, SessionCoordinator)
        - Kept legacy coordinator fields for backward compatibility during migration
        - Will be cleaned up in Phase 4 after MainViewModel is fully refactored
    """

    # Core infrastructure
    root: Any  # tk.Tk
    settings_obj: Settings
    event_bus: EventBus | None
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
    project_lifecycle_coordinator: ProjectLifecycleCoordinator | None = None
    hardware_coordinator: HardwareCoordinator | None = None
    processing_coordinator: VideoProcessingCoordinator | None = None
    recording_session_coordinator: RecordingSessionCoordinator | None = None
    live_camera_session_coordinator: LiveCameraSessionCoordinator | None = None
    live_calibration_coordinator: LiveCalibrationCoordinator | None = None
    project_workflow_adapter: ProjectWorkflowAdapter | None = None
    live_batch_coordinator: LiveBatchCoordinator | None = None  # v2.3.0

    # LEGACY coordinators — migrate consumers in Phase 4
    detector_coordinator: Any = None  # LEGACY: Migrate to hardware_coordinator

    # Runtime State
    cancel_event: Any = None

    # Testing
    test_sync_event: Any = None
