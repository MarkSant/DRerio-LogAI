from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

from zebtrack.analysis.analysis_service import AnalysisService

# Phase 3: Super Coordinators (replace legacy coordinators/orchestrators)
from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.session_coordinator import SessionCoordinator
from zebtrack.coordinators.ui_state_coordinator import UIStateController
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

    # Phase 3: Super Coordinators (NEW - replace 20 legacy coordinators)
    project_lifecycle_coordinator: ProjectLifecycleCoordinator | None = None
    hardware_coordinator: HardwareCoordinator | None = None
    processing_coordinator: ProcessingCoordinator | None = None
    session_coordinator: SessionCoordinator | None = None
    project_workflow_adapter: ProjectWorkflowAdapter | None = None
    live_batch_coordinator: LiveBatchCoordinator | None = None  # v2.3.0

    # LEGACY coordinators — still used at runtime; migrate consumers in Phase 4
    analysis_coordinator: Any = None  # LEGACY: Migrate to processing_coordinator
    video_orchestrator: Any = None  # LEGACY: Migrate to processing_coordinator
    recording_coordinator: Any = None  # LEGACY: Migrate to session_coordinator
    live_camera_coordinator: Any = None  # LEGACY: Migrate to session_coordinator
    detector_coordinator: Any = None  # LEGACY: Migrate to hardware_coordinator

    # Runtime State
    cancel_event: Any = None

    # Testing
    test_sync_event: Any = None
