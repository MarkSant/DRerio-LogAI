"""Coordinators Package - Orchestrators for ZebTrack-AI Refactoring.

This package contains coordinator classes that orchestrate complex workflows
by delegating to services. Part of the v4.0 refactoring plan.

Available Coordinators:
    BaseCoordinator - Abstract base class for all coordinators
    DialogCoordinator - Dialog management (Phase 1)
    HardwareCoordinator - Hardware management (Phase 3)
    ProcessingCoordinator - Processing workflows (Phase 3)
    ProjectLifecycleCoordinator - Project lifecycle (Phase 3)
    SessionCoordinator - Session management (Phase 3)

See:
    docs/REFACTOR-MASTER-PLAN-2025.md - Complete refactoring plan
"""

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.processing_coordinator import (
    ProcessingCoordinator,
    ProcessingCoordinatorError,
)
from zebtrack.coordinators.project_lifecycle_coordinator import (
    ProjectLifecycleCoordinator,
)
from zebtrack.coordinators.session_coordinator import SessionCoordinator

__all__ = [
    "BaseCoordinator",
    "CoordinatorDependencyError",
    "CoordinatorError",
    "CoordinatorValidationError",
    "DialogCoordinator",
    "HardwareCoordinator",
    "ProcessingCoordinator",
    "ProcessingCoordinatorError",
    "ProjectLifecycleCoordinator",
    "SessionCoordinator",
]
