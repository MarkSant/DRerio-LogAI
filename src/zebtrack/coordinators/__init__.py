"""Coordinators Package - Orchestrators for DRerio LogAI.

This package contains coordinator classes that orchestrate complex workflows
by delegating to services.

Available Coordinators:
    BaseCoordinator - Unified base class for all coordinators
    CalibrationCoordinator - Calibration scope and context management (Phase 5B)
    ProjectCoordinator - Project lifecycle management (Sprint 3)
    DetectorSetupCoordinator - Detector setup and configuration (Phase 4.9)
    ModelDiagnosticsCoordinator - Model diagnostic tests (Phase 4.9)
    VideoProcessingCoordinator - Core video processing workflow (Phase 4)
    ProgressTrackingCoordinator - Processing progress and batch context (Phase 4)
    MultiAquariumCoordinator - Aquarium detection and zone management (Phase 4)
    SequentialProcessingCoordinator - Sequential multi-aquarium processing (Phase 4)
    ReportGenerationCoordinator - Report generation workflows (Phase 4)
    RecordingSessionCoordinator - Recording session lifecycle (Phase 4.7)
    LiveCameraSessionCoordinator - Live camera analysis sessions (Phase 4.7)
    LiveCalibrationCoordinator - Camera calibration and zone validation (Phase 4.7)
    ProjectLifecycleCoordinator - Project lifecycle (Phase 3 super coordinator)
    UIStateController - UI state synchronization (moved from orchestrators/)
"""

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.coordinators.calibration_coordinator import CalibrationCoordinator
from zebtrack.coordinators.detector_setup_coordinator import (
    DetectorSetupCoordinator,
    DetectorSetupCoordinatorError,
)
from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
from zebtrack.coordinators.live_calibration_coordinator import (
    LiveCalibrationCoordinator,
    LiveCalibrationCoordinatorError,
)
from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
)
from zebtrack.coordinators.model_diagnostics_coordinator import (
    DiagnosticAbortError,
    ModelDiagnosticsCoordinator,
    ModelDiagnosticsCoordinatorError,
)
from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.processing_types import ProcessingCoordinatorError
from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator
from zebtrack.coordinators.project_coordinator import (
    ProjectCoordinator,
    ProjectCoordinatorError,
)
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.recording_session_coordinator import (
    RecordingSessionCoordinator,
    RecordingSessionCoordinatorError,
)
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.sequential_processing_coordinator import (
    SequentialProcessingCoordinator,
)
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator

__all__ = [
    "BaseCoordinator",
    "CalibrationCoordinator",
    "CoordinatorDependencyError",
    "CoordinatorError",
    "CoordinatorValidationError",
    "DetectorSetupCoordinator",
    "DetectorSetupCoordinatorError",
    "DiagnosticAbortError",
    "DialogCoordinator",
    "LiveBatchCoordinator",
    "LiveCalibrationCoordinator",
    "LiveCalibrationCoordinatorError",
    "LiveCameraSessionCoordinator",
    "LiveCameraSessionCoordinatorError",
    "ModelDiagnosticsCoordinator",
    "ModelDiagnosticsCoordinatorError",
    "MultiAquariumCoordinator",
    "ProcessingCoordinatorError",
    "ProgressTrackingCoordinator",
    "ProjectCoordinator",
    "ProjectCoordinatorError",
    "ProjectLifecycleCoordinator",
    "RecordingSessionCoordinator",
    "RecordingSessionCoordinatorError",
    "ReportGenerationCoordinator",
    "SequentialProcessingCoordinator",
    "UIStateController",
    "VideoProcessingCoordinator",
]
