"""Base Coordinator for ZebTrack-AI Refactoring.

This module provides the abstract base class for all coordinators in the
refactored architecture. Coordinators are responsible for orchestrating
complex workflows by delegating to services.

Architecture Pattern:
- Coordinators orchestrate workflows
- Services provide business logic
- Repositories handle I/O
- Models represent data

Example:
    ```python
    from zebtrack.coordinators.base import BaseCoordinator

    class ProjectCoordinator(BaseCoordinator):
        def __init__(self, state_manager, project_manager, **kwargs):
            super().__init__(state_manager=state_manager)
            self.project_manager = project_manager

        def create_project(self, name: str) -> Path:
            # Orchestrate project creation workflow
            ...
    ```

See Also:
    - docs/REFACTOR-MASTER-PLAN-2025.md - Refactoring strategy
    - docs/ARCHITECTURE.md - Overall architecture
    - docs/DEPENDENCY_INJECTION_GUIDE.md - DI patterns
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class BaseCoordinator(ABC):
    """
    Abstract base class for all coordinators.

    Coordinators follow the orchestrator pattern:
    1. Accept injected dependencies (DI)
    2. Delegate business logic to services
    3. Update state via StateManager
    4. Publish events via EventBus
    5. Return results or raise exceptions

    Design Principles:
    - Single Responsibility: One coordinator per workflow domain
    - Dependency Injection: All dependencies injected via __init__
    - Stateless: No mutable state except configuration
    - Observable: Use StateManager for observable state changes
    - Testable: Easy to mock all dependencies

    Attributes:
        state_manager: Centralized state management
        event_bus: Optional event bus for UI notifications

    Example Workflow:
        ```python
        coordinator = ProjectCoordinator(state_manager, project_manager)

        try:
            result = coordinator.create_project(name="my_project")
            # State automatically updated via state_manager
            # Events automatically published via event_bus
            return result
        except CoordinatorError as e:
            # Handle error
            log.error("workflow.failed", error=str(e))
            raise
        ```
    """

    def __init__(
        self,
        state_manager: StateManager,
        event_bus: EventBus | None = None,
    ):
        """Initialize base coordinator.

        Args:
            state_manager: Required StateManager for state tracking
            event_bus: Optional EventBus for UI notifications
        """
        self.state_manager = state_manager
        self.event_bus = event_bus

        # Log coordinator initialization
        coordinator_name = self.__class__.__name__
        log.info(
            "coordinator.initialized",
            coordinator=coordinator_name,
            has_event_bus=event_bus is not None,
        )

    @abstractmethod
    def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available.

        This method should be implemented by subclasses to check that
        all injected dependencies are valid and ready for use.

        Returns:
            True if all dependencies are valid, False otherwise

        Example:
            ```python
            def validate_dependencies(self) -> bool:
                if self.project_manager is None:
                    log.error("dependency.missing", dep="project_manager")
                    return False
                if not self.project_manager.is_initialized():
                    log.error("dependency.not_ready", dep="project_manager")
                    return False
                return True
            ```
        """
        pass

    def _update_state(self, category: Any, **kwargs):
        """
        Helper method to update state via StateManager.

        Args:
            category: StateCategory enum value
            **kwargs: State fields to update

        Example:
            ```python
            self._update_state(
                StateCategory.PROJECT,
                project_path=new_path,
                project_name="my_project",
            )
            ```
        """
        source = f"{self.__class__.__name__}.{self._get_caller_method()}"

        # Dispatch to appropriate state update method
        if hasattr(self.state_manager, f"update_{category.name.lower()}_state"):
            update_method = getattr(self.state_manager, f"update_{category.name.lower()}_state")
            update_method(source=source, **kwargs)
        else:
            log.warning(
                "state.category.unknown",
                category=category.name,
                coordinator=self.__class__.__name__,
            )

    def _publish_event(self, event_name: str, data: dict[str, Any] | None = None):
        """
        Helper method to publish events via EventBus.

        Args:
            event_name: Event name (from Events enum)
            data: Optional event data

        Example:
            ```python
            self._publish_event(
                Events.PROJECT_CREATED,
                {"project_name": "my_project", "path": str(path)},
            )
            ```
        """
        if self.event_bus:
            self.event_bus.publish_event(event_name, data or {})
        else:
            log.debug(
                "event.no_bus",
                event=event_name,
                coordinator=self.__class__.__name__,
            )

    def _get_caller_method(self) -> str:
        """Get the name of the calling method for logging."""
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back and frame.f_back.f_back:
            return frame.f_back.f_back.f_code.co_name
        return "unknown"

    def _validate_not_none(self, value: Any, name: str):
        """
        Validate that a value is not None.

        Args:
            value: Value to check
            name: Name of the value for error messages

        Raises:
            ValueError: If value is None
        """
        if value is None:
            error_msg = f"Required parameter '{name}' cannot be None"
            log.error(
                "validation.failed",
                parameter=name,
                coordinator=self.__class__.__name__,
            )
            raise ValueError(error_msg)

    def _validate_type(self, value: Any, expected_type: type, name: str):
        """
        Validate that a value is of expected type.

        Args:
            value: Value to check
            expected_type: Expected type
            name: Name of the value for error messages

        Raises:
            TypeError: If value is not of expected type
        """
        if not isinstance(value, expected_type):
            error_msg = (
                f"Parameter '{name}' must be of type {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
            log.error(
                "validation.type_mismatch",
                parameter=name,
                expected=expected_type.__name__,
                actual=type(value).__name__,
                coordinator=self.__class__.__name__,
            )
            raise TypeError(error_msg)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(state_manager={self.state_manager})>"


class CoordinatorError(Exception):
    """Base exception for coordinator errors."""

    def __init__(self, message: str, coordinator: str | None = None, **context):
        """
        Initialize coordinator error.

        Args:
            message: Error message
            coordinator: Name of the coordinator that raised the error
            **context: Additional context for debugging
        """
        super().__init__(message)
        self.coordinator = coordinator
        self.context = context

        # Log error with full context
        log.error(
            "coordinator.error",
            message=message,
            coordinator=coordinator,
            **context,
        )


class CoordinatorValidationError(CoordinatorError):
    """Raised when coordinator validation fails."""
    pass


class CoordinatorDependencyError(CoordinatorError):
    """Raised when required dependencies are missing or invalid."""
    pass
