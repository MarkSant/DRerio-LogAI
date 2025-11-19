from dataclasses import dataclass
from typing import Any, Optional

from zebtrack.core.analysis_coordinator import AnalysisCoordinator
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.hardware_coordinator import HardwareCoordinator
from zebtrack.core.model_service import ModelService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.project_workflow_service import ProjectWorkflowService
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.video_orchestrator import VideoOrchestrator
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.weight_manager import WeightManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus import EventBus
from zebtrack.coordinators.project_coordinator import ProjectCoordinator
from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.core.recording_service import RecordingService

@dataclass
class MainViewModelDependencies:
    """
    Encapsulates all dependencies required by MainViewModel.

    This reduces the number of arguments in MainViewModel.__init__ and
    makes dependency injection more structured.
    """
    root: Any  # tk.Tk
    settings_obj: Settings
    event_bus: Optional[EventBus]
    state_manager: StateManager
    ui_coordinator: UICoordinator
    project_manager: ProjectManager
    project_workflow_service: ProjectWorkflowService
    weight_manager: WeightManager
    model_service: ModelService
    detector_service: DetectorService
    video_processing_service: VideoProcessingService

    # Optional services
    analysis_service: Optional[AnalysisService] = None
    recording_service: Optional[RecordingService] = None
    live_camera_service: Any = None

    # Coordinators
    hardware_coordinator: Optional[HardwareCoordinator] = None
    analysis_coordinator: Optional[AnalysisCoordinator] = None
    video_orchestrator: Optional[VideoOrchestrator] = None
    recording_coordinator: Any = None
    live_camera_coordinator: Any = None
    detector_coordinator: Any = None
    processing_coordinator: Any = None
    project_coordinator: Optional[ProjectCoordinator] = None

    # Testing
    test_sync_event: Any = None
