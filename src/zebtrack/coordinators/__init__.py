"""Coordinators Package - Orchestrators for ZebTrack-AI Refactoring.

This package contains coordinator classes that orchestrate complex workflows
by delegating to services. Part of the v4.0 refactoring plan.

Available Coordinators:
    BaseCoordinator - Abstract base class for all coordinators
    ProjectCoordinator - Project lifecycle management (Sprint 3)

Planned Coordinators (Sprint 4-6):
    DetectorCoordinator - Detector setup and configuration
    RecordingCoordinator - Recording and Arduino management
    LiveCameraCoordinator - Live camera analysis sessions
    ProcessingCoordinator - Video processing workflows

See:
    docs/REFACTOR-MASTER-PLAN-2025.md - Complete refactoring plan
"""

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.coordinators.project_coordinator import (
    ProjectCoordinator,
    ProjectCoordinatorError,
)

__all__ = [
    "BaseCoordinator",
    "CoordinatorError",
    "CoordinatorValidationError",
    "CoordinatorDependencyError",
    "ProjectCoordinator",
    "ProjectCoordinatorError",
]
