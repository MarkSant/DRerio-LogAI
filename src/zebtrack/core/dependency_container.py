from dataclasses import dataclass
from typing import Any, Optional

from zebtrack.analysis.analysis_service import AnalysisService

# Phase 3: Super Coordinators (replace legacy coordinators/orchestrators)
from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.session_coordinator import SessionCoordinator
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.live_camera_service import LiveCameraService
from zebtrack.core.model_service import ModelService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.weight_manager import WeightManager
from zebtrack.orchestrators.ui_state_controller import UIStateController
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
    event_bus: Optional[EventBus]
    state_manager: StateManager
    ui_coordinator: UICoordinator

    # Domain managers
    project_manager: ProjectManager
    project_workflow_service: ProjectWorkflowService
    weight_manager: WeightManager
    model_service: ModelService

    # Domain services
    detector_service: DetectorService
    video_processing_service: VideoProcessingService
    analysis_service: Optional[AnalysisService] = None
    recording_service: Optional[RecordingService] = None
    live_camera_service: Optional[LiveCameraService] = None
    ui_state_controller: Optional[UIStateController] = None

    # Phase 3: Super Coordinators (NEW - replace 20 legacy coordinators)
    project_lifecycle_coordinator: Optional[ProjectLifecycleCoordinator] = None
    hardware_coordinator: Optional[HardwareCoordinator] = None
    processing_coordinator: Optional[ProcessingCoordinator] = None
    session_coordinator: Optional[SessionCoordinator] = None
    project_workflow_adapter: Optional[ProjectWorkflowAdapter] = None

    # Legacy coordinators (DEPRECATED - will be removed in Phase 4)
    # Kept temporarily for backward compatibility during gradual migration
    analysis_coordinator: Any = None  # DEPRECATED: Use processing_coordinator
    video_orchestrator: Any = None  # DEPRECATED: Use processing_coordinator
    recording_coordinator: Any = None  # DEPRECATED: Use session_coordinator
    live_camera_coordinator: Any = None  # DEPRECATED: Use session_coordinator
    detector_coordinator: Any = None  # DEPRECATED: Use hardware_coordinator
    project_coordinator: Any = None  # DEPRECATED: Use project_lifecycle_coordinator

    # Testing
    test_sync_event: Any = None
