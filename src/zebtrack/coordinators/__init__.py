"""Coordinators Package - Orchestrators for ZebTrack-AI Refactoring.

This package contains coordinator classes that orchestrate complex workflows
by delegating to services. Part of the v4.0 refactoring plan.

Available Coordinators:
    BaseCoordinator - Abstract base class for all coordinators
    ProjectCoordinator - Project lifecycle management (Sprint 3)
    RecordingCoordinator - Recording and Arduino management (Sprint 4)
    LiveCameraCoordinator - Live camera analysis sessions (Sprint 4)
    DetectorCoordinator - Detector setup and configuration (Sprint 5)
    ProcessingCoordinator - Video processing workflows (Sprint 6)

See:
    docs/REFACTOR-MASTER-PLAN-2025.md - Complete refactoring plan
"""

from zebtrack.coordinators.base import (
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
from zebtrack.coordinators.processing_coordinator import (
    ProcessingCoordinator,
    ProcessingCoordinatorError,
)
from zebtrack.coordinators.project_coordinator import (
    ProjectCoordinator,
    ProjectCoordinatorError,
)
from zebtrack.coordinators.recording_coordinator import (
    RecordingCoordinator,
    RecordingCoordinatorError,
)

__all__ = [
    "BaseCoordinator",
    "CoordinatorError",
    "CoordinatorValidationError",
    "CoordinatorDependencyError",
    "ProjectCoordinator",
    "ProjectCoordinatorError",
    "RecordingCoordinator",
    "RecordingCoordinatorError",
    "LiveCameraCoordinator",
    "LiveCameraCoordinatorError",
    "DetectorCoordinator",
    "DetectorCoordinatorError",
    "ProcessingCoordinator",
    "ProcessingCoordinatorError",
]
