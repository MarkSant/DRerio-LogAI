"""Coordinators Package - Orchestrators for ZebTrack-AI.

This package contains coordinator classes that orchestrate complex workflows
by delegating to services.

Available Coordinators:
    BaseCoordinator - Unified base class for all coordinators
    ProjectCoordinator - Project lifecycle management (Sprint 3)
    RecordingCoordinator - Recording and Arduino management (Sprint 4)
    LiveCameraCoordinator - Live camera analysis sessions (Sprint 4)
    DetectorCoordinator - Detector setup and configuration (Sprint 5)
    VideoProcessingCoordinator - Core video processing workflow (Phase 4)
    ProgressTrackingCoordinator - Processing progress and batch context (Phase 4)
    MultiAquariumCoordinator - Aquarium detection and zone management (Phase 4)
    SequentialProcessingCoordinator - Sequential multi-aquarium processing (Phase 4)
    ReportGenerationCoordinator - Report generation workflows (Phase 4)
    SessionCoordinator - Session management (Phase 3 super coordinator)
    HardwareCoordinator - Hardware setup (Phase 3 super coordinator)
    ProjectLifecycleCoordinator - Project lifecycle (Phase 3 super coordinator)
    UIStateController - UI state synchronization (moved from orchestrators/)
"""

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.coordinators.detector_coordinator import (
    DetectorCoordinator,
    DetectorCoordinatorError,
)
from zebtrack.coordinators.live_camera_coordinator import (
    LiveCameraCoordinator,
    LiveCameraCoordinatorError,
)
from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.processing_types import ProcessingCoordinatorError
from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator
from zebtrack.coordinators.project_coordinator import (
    ProjectCoordinator,
    ProjectCoordinatorError,
)
from zebtrack.coordinators.recording_coordinator import (
    RecordingCoordinator,
    RecordingCoordinatorError,
)
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.sequential_processing_coordinator import (
    SequentialProcessingCoordinator,
)
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator

__all__ = [
    "BaseCoordinator",
    "CoordinatorDependencyError",
    "CoordinatorError",
    "CoordinatorValidationError",
    "DetectorCoordinator",
    "DetectorCoordinatorError",
    "LiveCameraCoordinator",
    "LiveCameraCoordinatorError",
    "MultiAquariumCoordinator",
    "ProcessingCoordinatorError",
    "ProgressTrackingCoordinator",
    "ProjectCoordinator",
    "ProjectCoordinatorError",
    "RecordingCoordinator",
    "RecordingCoordinatorError",
    "ReportGenerationCoordinator",
    "SequentialProcessingCoordinator",
    "UIStateController",
    "VideoProcessingCoordinator",
]
