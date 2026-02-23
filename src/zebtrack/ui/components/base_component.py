"""Base UI Component for large-scale UI orchestration.

This module provides abstract base classes for UI components that orchestrate
multiple widgets and manage complex UI layouts. Complements BaseWidget for
higher-level UI patterns.

Architecture Pattern:
- BaseUIComponent: For managers and orchestrators (MenuManager, LayoutManager)
- BaseWidget: For individual widgets (buttons, frames)

Example:
    ```python
    from zebtrack.ui.components.base_component import BaseUIComponent

    class LayoutManager(BaseUIComponent):
        def __init__(self, parent, controller, event_bus, settings_obj):
            super().__init__(parent, controller, event_bus, settings_obj)

        def setup_widgets(self):
            # Create and layout all panels
            ...

        def bind_events(self):
            # Bind keyboard shortcuts, etc.
            ...
    ```

See Also:
    - base.py - BaseWidget for individual widgets
    - docs/REFACTOR-MASTER-PLAN-2025.md - Refactoring strategy
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from tkinter import Frame, Misc
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.event_bus_v2 import EVENT_NAME_TO_UIEVENT, Event, EventBusV2, UIEvents

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class BaseUIComponent(ABC):
    """
    Abstract base class for large UI components (managers, layouts).

    UI Components follow a structured lifecycle:
    1. __init__: Store dependencies
    2. setup_widgets(): Create and layout widgets
    3. bind_events(): Bind event handlers
    4. show(): Make component visible
    5. hide(): Hide component
    6. cleanup(): Release resources

    Design Principles:
    - Dependency Injection: All deps via __init__
    - Separation of Concerns: Widget creation separate from event binding
    - Lifecycle Management: Clear setup and cleanup phases
    - Event-Driven: Use EventBusV2 for loose coupling
    - Testable: Easy to mock dependencies

    Attributes:
        parent: Tkinter parent widget
        controller: MainViewModel or coordinator
        event_bus: Event bus for notifications
        settings: Application settings
        frame: Root frame for this component

    Example:
        ```python
        class MenuManager(BaseUIComponent):
            def setup_widgets(self):
                self.menubar = tk.Menu(self.parent)
                self.file_menu = tk.Menu(self.menubar, tearoff=0)
                # ...

            def bind_events(self):
                # No event binding needed for menus
                pass

            def create_file_menu(self):
                # Helper method for menu creation
                ...
        ```
    """

    def __init__(
        self,
        parent: Misc,
        controller: Any,
        event_bus: EventBusV2 | None,
        settings_obj: Settings,
    ):
        """Initialize base UI component.

        Args:
            parent: Tkinter parent widget
            controller: Controller (MainViewModel or coordinator)
            event_bus: Optional EventBusV2 for notifications
            settings_obj: Application settings
        """
        self.parent = parent
        self.controller = controller
        self.event_bus = event_bus
        self.settings = settings_obj

        # Create root frame for this component
        self.frame = Frame(parent)

        # Component state
        self._initialized = False
        self._visible = False

        # Logging
        component_name = self.__class__.__name__
        self._log = log.bind(component=component_name)

        self._log.info("component.initialized", has_event_bus=event_bus is not None)

    @abstractmethod
    def setup_widgets(self):
        """
        Create and layout all widgets for this component.

        This method should:
        - Create all child widgets
        - Configure layout (pack, grid, place)
        - Set initial widget states
        - NOT bind events (use bind_events for that)

        Called during component initialization.

        Example:
            ```python
            def setup_widgets(self):
                # Create toolbar
                self.toolbar_frame = ttk.Frame(self.frame)
                self.toolbar_frame.pack(side="top", fill="x")

                # Create buttons
                self.run_button = ttk.Button(
                    self.toolbar_frame,
                    text="Run",
                    command=self._on_run_clicked,
                )
                self.run_button.pack(side="left")
            ```
        """
        pass

    @abstractmethod
    def bind_events(self):
        """
        Bind event handlers for this component.

        This method should:
        - Bind keyboard shortcuts
        - Subscribe to event bus events
        - Bind widget callbacks
        - Set up state observers

        Called after setup_widgets().

        Example:
            ```python
            def bind_events(self):
                # Keyboard shortcuts
                self.frame.bind("<Control-r>", lambda e: self._on_run_clicked())

                # Event bus subscriptions
                if self.event_bus:
                    self.event_bus.subscribe(
                        UIEvents.PROJECT_LOADED,
                        self._on_project_loaded,
                    )

                # State manager observers
                self.controller.state_manager.subscribe(
                    StateCategory.PROCESSING,
                    self._on_processing_state_changed,
                )
            ```
        """
        pass

    def show(self):
        """Make this component visible."""
        if not self._initialized:
            self.setup_widgets()
            self.bind_events()
            self._initialized = True

        self.frame.pack(fill="both", expand=True)
        self._visible = True
        self._log.debug("component.shown")

    def hide(self):
        """Hide this component."""
        self.frame.pack_forget()
        self._visible = False
        self._log.debug("component.hidden")

    def is_visible(self) -> bool:
        """Check if component is currently visible."""
        return self._visible

    def cleanup(self):
        """
        Clean up resources before component destruction.

        Override this method to:
        - Unsubscribe from events
        - Release file handles
        - Stop background threads
        - Clear caches

        Example:
            ```python
            def cleanup(self):
                # Unsubscribe from event bus
                if self.event_bus:
                    self.event_bus.unsubscribe_all(self)

                # Stop background tasks
                if hasattr(self, 'update_timer'):
                    self.parent.after_cancel(self.update_timer)

                super().cleanup()
            ```
        """
        self._log.info("component.cleanup")

    def _emit_event(self, event_type: UIEvents | str, data: dict[str, Any] | None = None):
        """
        Helper to emit events via EventBusV2.

        Args:
            event_type: UIEvents enum member or legacy string name.
            data: Optional event data.
        """
        if self.event_bus:
            if isinstance(event_type, str):
                resolved = EVENT_NAME_TO_UIEVENT.get(event_type)
                if resolved is None:
                    self._log.warning("component.event.unknown_string", event_name=event_type)
                    return
                event_type = resolved
            self.event_bus.publish(Event(type=event_type, data=data or {}))
            self._log.debug("component.event.emitted", event_type=event_type.name)
        else:
            self._log.debug("component.event.no_bus", event_type=str(event_type))

    def _schedule_on_ui(self, func, *args, **kwargs):
        """
        Schedule a function to run on the UI thread.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Example:
            ```python
            def update_progress(self, progress: int):
                # Safe to call from background thread
                self._schedule_on_ui(self._update_progress_ui, progress)

            def _update_progress_ui(self, progress: int):
                # Runs on UI thread
                self.progress_bar['value'] = progress
            ```
        """
        self.parent.after(0, func, *args, **kwargs)

    def _validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are present.

        Returns:
            True if all dependencies valid, False otherwise
        """
        if self.parent is None:
            self._log.error("dependency.missing", dep="parent")
            return False

        if self.controller is None:
            self._log.error("dependency.missing", dep="controller")
            return False

        if self.settings is None:
            self._log.error("dependency.missing", dep="settings")
            return False

        return True

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<{self.__class__.__name__}(visible={self._visible}, initialized={self._initialized})>"
        )


class UIComponentError(Exception):
    """Base exception for UI component errors."""

    def __init__(self, message: str, component: str | None = None, **context):
        """
        Initialize UI component error.

        Args:
            message: Error message
            component: Name of the component that raised the error
            **context: Additional context for debugging
        """
        super().__init__(message)
        self.component = component
        self.context = context

        log.error(
            "ui_component.error",
            message=message,
            component=component,
            **context,
        )
