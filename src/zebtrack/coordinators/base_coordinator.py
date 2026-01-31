"""Base class for all coordinators.

Created in Phase 3 of MainViewModel refactoring to provide a common base
for all super coordinators without dependency on MainViewModel.

CRITICAL: This base class NEVER takes MainViewModel as dependency.
All dependencies must be injected explicitly.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus import EventBus

import structlog

log = structlog.get_logger()


class BaseCoordinator:
    """Base class for all coordinators (Phase 3 refactoring).

    Provides common functionality without coupling to MainViewModel.
    All coordinators inherit from this base to ensure:
    1. No direct MainViewModel dependency (breaks circular dependency)
    2. Consistent state management interface
    3. Optional event bus integration
    4. Structured logging

    Attributes:
        state_manager: Centralized state management
        event_bus: Optional event bus for publishing events
        logger: Structured logger for this coordinator

    Example:
        class ProjectLifecycleCoordinator(BaseCoordinator):
            def __init__(
                self,
                state_manager: StateManager,
                project_manager: ProjectManager,
                event_bus: EventBus | None = None
            ):
                super().__init__(state_manager, event_bus)
                self.project_manager = project_manager

            def create_project(self, name: str) -> Path:
                self.logger.info("project.create.start", name=name)
                # Implementation...
                self._publish_event("PROJECT_CREATED", {"name": name})
                return project_path
    """

    def __init__(
        self,
        state_manager: "StateManager",
        event_bus: "EventBus | None" = None,
    ):
        """Initialize base coordinator.

        Args:
            state_manager: StateManager instance for state updates
            event_bus: Optional EventBus for publishing events

        Note:
            NEVER pass MainViewModel here. All dependencies must be
            injected explicitly to avoid circular dependencies.
        """
        self.state_manager = state_manager
        self.event_bus = event_bus
        self.logger = structlog.get_logger(self.__class__.__name__)

    def _publish_event(self, event_name: str, event_data: dict | None = None) -> None:
        """Publish event to event bus if available.

        Args:
            event_name: Name of the event to publish
            event_data: Optional data payload for the event

        Note:
            Silently ignores if event_bus is not configured.
        """
        if self.event_bus is not None:
            self.event_bus.publish_event(event_name, event_data or {})
            self.logger.debug("event.published", event_name=event_name)

    def _update_state(self, category: str, key: str, value) -> None:
        """Update state manager.

        Args:
            category: State category (e.g., "project", "processing")
            key: State key
            value: New value

        Example:
            self._update_state("project", "project_name", "my_project")
        """
        from zebtrack.core.state_manager import StateCategory

        # Convert string to StateCategory enum if needed
        if isinstance(category, str):
            category = StateCategory[category.upper()]

        self.state_manager.update(category, key, value)
        self.logger.debug("state.updated", category=category.value, key=key)

    def _get_state(self, category: str, key: str, default=None):
        """Get value from state manager.

        Args:
            category: State category
            key: State key
            default: Default value if key not found

        Returns:
            State value or default

        Example:
            project_name = self._get_state("project", "project_name")
        """
        from zebtrack.core.state_manager import StateCategory

        if isinstance(category, str):
            category = StateCategory[category.upper()]

        state = self.state_manager.get_state(category)
        return state.get(key, default)
