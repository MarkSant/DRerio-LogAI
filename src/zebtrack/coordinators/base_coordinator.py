"""Unified Base Coordinator for ZebTrack-AI.

Provides the single base class for ALL coordinators in the application.
Unified in Phase 3 from two prior implementations (base.py ABC and
base_coordinator.py concrete) into one consistent concrete class.

Architecture Pattern:
    - Coordinators orchestrate workflows
    - Services provide business logic
    - Repositories handle I/O
    - Models represent data

CRITICAL: This base class NEVER takes MainViewModel as dependency.
All dependencies must be injected explicitly.

History:
    - Phase 3 (original): Created as concrete base for super coordinators
    - Phase 3 (refactoring, Feb 2026): Unified with ABC base — absorbed
      ``validate_dependencies``, ``_validate_not_none``, ``_validate_type``,
      ``_get_caller_method``, and exception classes from the former
      ``base.py``.  ABC enforcement removed; concrete default provided.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class BaseCoordinator:
    """Unified base class for all coordinators.

    Provides common functionality without coupling to MainViewModel.
    All coordinators inherit from this base to ensure:

    1. No direct MainViewModel dependency (breaks circular dependency)
    2. Consistent state management interface
    3. Optional event bus integration
    4. Structured logging
    5. Dependency validation helpers
    6. Type/value validation helpers

    Attributes:
        state_manager: Centralized state management
        event_bus: Optional event bus for publishing events
        logger: Structured logger for this coordinator

    Example:
        .. code-block:: python

            class ProjectLifecycleCoordinator(BaseCoordinator):
                def __init__(
                    self,
                    state_manager: StateManager,
                    project_manager: ProjectManager,
                    event_bus: EventBus | None = None,
                ):
                    super().__init__(state_manager, event_bus)
                    self.project_manager = project_manager

                def validate_dependencies(self) -> bool:
                    return self.project_manager is not None

                def create_project(self, name: str) -> Path:
                    self.logger.info("project.create.start", name=name)
                    self._publish_event("PROJECT_CREATED", {"name": name})
                    return project_path
    """

    def __init__(
        self,
        state_manager: StateManager,
        event_bus: EventBus | None = None,
    ):
        """Initialize base coordinator.

        Args:
            state_manager: StateManager instance for state updates.
            event_bus: Optional EventBus for publishing events.

        Note:
            NEVER pass MainViewModel here.  All dependencies must be
            injected explicitly to avoid circular dependencies.
        """
        self.state_manager = state_manager
        self.event_bus = event_bus
        self.logger = structlog.get_logger(self.__class__.__name__)

        # Log coordinator initialization
        self.logger.info(
            "coordinator.initialized",
            coordinator=self.__class__.__name__,
            has_event_bus=event_bus is not None,
        )

    # ------------------------------------------------------------------
    # Dependency validation
    # ------------------------------------------------------------------

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are available.

        Subclasses should override this to check that all injected
        dependencies are valid and ready for use.  The default
        implementation returns ``True`` (no extra dependencies).

        Returns:
            True if all dependencies are valid, False otherwise.

        Example:
            .. code-block:: python

                def validate_dependencies(self) -> bool:
                    if self.project_manager is None:
                        self.logger.error("dependency.missing", dep="project_manager")
                        return False
                    return True
        """
        return True

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _update_state(self, category: Any, **kwargs: Any) -> None:
        """Update state via StateManager.

        Supports both ``StateCategory`` enum values and plain strings.
        Accepts arbitrary keyword arguments that are forwarded to the
        state manager as field updates.

        Args:
            category: ``StateCategory`` enum value **or** a string that
                will be upper-cased and converted to the enum.
            **kwargs: State fields to update.

        Example:
            .. code-block:: python

                self._update_state(
                    StateCategory.PROJECT,
                    project_path=new_path,
                    project_name="my_project",
                )
        """
        from zebtrack.core.state_manager import StateCategory

        source = f"{self.__class__.__name__}.{self._get_caller_method()}"

        # Normalise category to StateCategory enum
        cat_enum: StateCategory
        if isinstance(category, str):
            cat_enum = StateCategory[category.upper()]
        else:
            cat_enum = category  # type: ignore[assignment]

        # Prefer the unified API when available
        prefer_unified = getattr(self.state_manager, "prefer_unified_state_api", False)

        if prefer_unified:
            unified_updater = getattr(self.state_manager, "update_state", None)
            if callable(unified_updater):
                unified_updater(category, source=source, **kwargs)
                return

        # Fallback: dispatch to category-specific updater
        category_updater_name = f"update_{cat_enum.name.lower()}_state"
        if hasattr(self.state_manager, category_updater_name):
            update_method = getattr(self.state_manager, category_updater_name)
            update_method(source=source, **kwargs)
        else:
            # Last resort: generic update_state
            self.state_manager.update_state(cat_enum, **kwargs)

    def _get_state(self, category: str, key: str, default: Any = None) -> Any:
        """Get a value from state manager.

        Args:
            category: State category (e.g., ``"project"``, ``"processing"``).
            key: State key.
            default: Default value if key not found.

        Returns:
            State value or *default*.

        Example:
            .. code-block:: python

                project_name = self._get_state("project", "project_name")
        """
        from zebtrack.core.state_manager import StateCategory

        cat_enum: StateCategory
        if isinstance(category, str):
            cat_enum = StateCategory[category.upper()]
        else:
            cat_enum = category  # type: ignore[assignment]

        state = self.state_manager.get_state(cat_enum)
        return state.get(key, default)

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _publish_event(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event via EventBus.

        Args:
            event_name: Event name constant (from ``Events``).
            data: Optional event payload.

        Note:
            Silently ignores if *event_bus* is not configured.
        """
        if self.event_bus is not None:
            self.event_bus.publish_event(event_name, data or {})
            self.logger.debug("event.published", event_name=event_name)
        else:
            self.logger.debug(
                "event.no_bus",
                event_name=event_name,
                coordinator=self.__class__.__name__,
            )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_not_none(self, value: Any, name: str) -> None:
        """Validate that *value* is not ``None``.

        Args:
            value: Value to check.
            name: Name of the value for error messages.

        Raises:
            ValueError: If *value* is ``None``.
        """
        if value is None:
            error_msg = f"Required parameter '{name}' cannot be None"
            self.logger.error(
                "validation.failed",
                parameter=name,
                coordinator=self.__class__.__name__,
            )
            raise ValueError(error_msg)

    def _validate_type(
        self,
        value: Any,
        expected_type: type | tuple[type, ...],
        name: str,
    ) -> None:
        """Validate that *value* is of expected type.

        Args:
            value: Value to check.
            expected_type: Expected type or tuple of types.
            name: Name of the value for error messages.

        Raises:
            TypeError: If *value* is not of expected type.
        """
        if not isinstance(value, expected_type):
            if isinstance(expected_type, type):
                type_name = expected_type.__name__
            else:
                type_name = ", ".join(t.__name__ for t in expected_type)

            error_msg = (
                f"Parameter '{name}' must be of type {type_name}, got {type(value).__name__}"
            )
            self.logger.error(
                "validation.type_mismatch",
                parameter=name,
                expected=type_name,
                actual=type(value).__name__,
                coordinator=self.__class__.__name__,
            )
            raise TypeError(error_msg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_caller_method(self) -> str:
        """Return the name of the calling method for logging/source tracking."""
        frame = inspect.currentframe()
        if frame and frame.f_back and frame.f_back.f_back:
            return frame.f_back.f_back.f_code.co_name
        return "unknown"

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(state_manager={self.state_manager})>"


# ======================================================================
# Coordinator exception hierarchy
# ======================================================================


class CoordinatorError(Exception):
    """Base exception for coordinator errors.

    Attributes:
        coordinator: Name of the coordinator that raised the error.
        context: Additional context dictionary for debugging.
    """

    def __init__(
        self,
        message: str,
        coordinator: str | None = None,
        context: dict[str, Any] | None = None,
        **extra_context: Any,
    ):
        super().__init__(message)
        self.coordinator = coordinator
        merged_context = {**(context or {}), **extra_context}
        self.context = merged_context

        # Log error with full context
        log_context = dict(merged_context)
        log_context.pop("coordinator", None)
        log.error(
            "coordinator.error",
            message=message,
            coordinator=coordinator,
            **log_context,
        )


class CoordinatorValidationError(CoordinatorError):
    """Raised when coordinator validation fails."""


class CoordinatorDependencyError(CoordinatorError):
    """Raised when required dependencies are missing or invalid."""
