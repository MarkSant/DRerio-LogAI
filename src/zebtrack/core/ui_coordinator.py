"""
UI Coordinator Service for ZebTrack-AI.

Phase 4: UI Coordination Consolidation
Consolidates all UI scheduling and update operations into a single service,
reducing code duplication and improving testability.

This service provides:
- Thread-safe UI scheduling via root.after() or event bus
- Convenience methods for common UI operations
- Testable interface via dependency injection
- Centralized UI coordination logic
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import structlog

if TYPE_CHECKING:
    from tkinter import Tk
    from zebtrack.event_bus import EventBus

log = structlog.get_logger()


class UICoordinator:
    """
    Service for coordinating UI updates and scheduling.

    Phase 4: Consolidates UI scheduling logic from MainViewModel,
    making UI updates testable and reducing code duplication.

    Responsibilities:
    - Schedule callbacks on UI thread
    - Provide convenience methods for common UI operations
    - Support both event bus and direct Tkinter scheduling
    - Handle errors gracefully with fallbacks
    """

    def __init__(
        self,
        root: Tk | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize UICoordinator.

        Args:
            root: Tkinter root window for scheduling
            event_bus: Optional event bus for UI scheduling
        """
        self.root = root
        self.event_bus = event_bus
        log.info("ui_coordinator.initialized", has_root=root is not None)

    def schedule(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        """
        Schedule a function to run on the UI thread.

        Phase 4: Consolidates scheduling logic from _schedule_on_ui.

        This method attempts to schedule the function via:
        1. Event bus (if available)
        2. root.after(0, ...) (if root available)
        3. Direct execution as fallback

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
        """
        # Try event bus first
        if self.event_bus is not None:
            published = self.event_bus.publish_callable(func, *args, **kwargs)
            if published:
                return
            log.warning(
                "ui_coordinator.event_bus_failed",
                callback=getattr(func, "__name__", repr(func)),
            )

        # Try root.after
        if self.root is not None:
            try:
                self.root.after(0, lambda: func(*args, **kwargs))
                return
            except Exception as e:
                log.warning(
                    "ui_coordinator.after_failed",
                    callback=getattr(func, "__name__", repr(func)),
                    error=str(e),
                )

        # Fallback to direct execution
        try:
            func(*args, **kwargs)
        except Exception as e:
            log.error(
                "ui_coordinator.direct_execution_failed",
                callback=getattr(func, "__name__", repr(func)),
                error=str(e),
                exc_info=True,
            )

    def schedule_after(
        self, delay_ms: int, func: Callable, *args: Any, **kwargs: Any
    ) -> str | None:
        """
        Schedule a function to run after a delay.

        Phase 4: Wrapper for root.after with error handling.

        Args:
            delay_ms: Delay in milliseconds
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            str: Tkinter after ID, or None if scheduling failed
        """
        if self.root is None:
            log.warning("ui_coordinator.schedule_after_no_root")
            return None

        try:
            return self.root.after(delay_ms, lambda: func(*args, **kwargs))
        except Exception as e:
            log.error(
                "ui_coordinator.schedule_after_failed",
                delay_ms=delay_ms,
                callback=getattr(func, "__name__", repr(func)),
                error=str(e),
            )
            return None

    def cancel_scheduled(self, after_id: str) -> None:
        """
        Cancel a scheduled callback.

        Args:
            after_id: ID returned from schedule_after
        """
        if self.root is None or after_id is None:
            return

        try:
            self.root.after_cancel(after_id)
        except Exception as e:
            log.warning("ui_coordinator.cancel_failed", after_id=after_id, error=str(e))

    # === Convenience Methods for Common UI Operations ===

    def update_view(self, view: Any, method_name: str, *args: Any, **kwargs: Any) -> None:
        """
        Update view by calling one of its methods on UI thread.

        Phase 4: Generic method for view updates.

        Args:
            view: View object with methods to call
            method_name: Name of the method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
        """
        if view is None:
            log.warning("ui_coordinator.update_view_no_view", method=method_name)
            return

        # Check if method exists before scheduling
        try:
            method = getattr(view, method_name, None)
            if method is None or not callable(method):
                log.error(
                    "ui_coordinator.update_view_method_not_found",
                    method=method_name,
                    view_type=type(view).__name__,
                )
                return

            self.schedule(method, *args, **kwargs)
        except AttributeError:
            log.error(
                "ui_coordinator.update_view_attribute_error",
                method=method_name,
                view_type=type(view).__name__,
            )

    def set_status(self, view: Any, message: str) -> None:
        """
        Update status message in view.

        Phase 4: Convenience method for status updates.

        Args:
            view: View object with set_status method
            message: Status message to display
        """
        self.update_view(view, "set_status", message)

    def show_error(self, view: Any, title: str, message: str) -> None:
        """
        Show error dialog in view.

        Phase 4: Convenience method for error dialogs.

        Args:
            view: View object with show_error method
            title: Error dialog title
            message: Error message
        """
        self.update_view(view, "show_error", title, message)

    def show_info(self, view: Any, title: str, message: str) -> None:
        """
        Show info dialog in view.

        Phase 4: Convenience method for info dialogs.

        Args:
            view: View object with show_info method
            title: Info dialog title
            message: Info message
        """
        self.update_view(view, "show_info", title, message)

    def update_progress(self, view: Any, value: float) -> None:
        """
        Update progress bar in view.

        Phase 4: Convenience method for progress updates.

        Args:
            view: View object with update_progress method
            value: Progress value (0.0 to 1.0)
        """
        self.update_view(view, "update_progress", value)

    def update_button_state(self, view: Any, button_id: str, state: str) -> None:
        """
        Update button state in view.

        Phase 4: Convenience method for button state updates.

        Args:
            view: View object with update_button_state method
            button_id: Button identifier
            state: New button state (e.g., "normal", "disabled")
        """
        self.update_view(view, "update_button_state", button_id, state)

    def display_frame(self, view: Any, frame: Any) -> None:
        """
        Display a video frame in view.

        Phase 4: Convenience method for frame display.

        Args:
            view: View object with display_frame method
            frame: Frame to display
        """
        self.update_view(view, "display_frame", frame)

    def update_detection_overlay(
        self, view: Any, payload: dict, processing_info: dict | None = None
    ) -> None:
        """
        Update detection overlay in view.

        Phase 4: Convenience method for detection overlay updates.

        Args:
            view: View object with update_detection_overlay method
            payload: Detection payload data
            processing_info: Optional processing information
        """
        self.update_view(view, "update_detection_overlay", payload, processing_info)

    def show_progress_bar(self, view: Any) -> None:
        """Show progress bar in view."""
        self.update_view(view, "show_progress_bar")

    def hide_progress_bar(self, view: Any) -> None:
        """Hide progress bar in view."""
        self.update_view(view, "hide_progress_bar")

    def update_idletasks(self, view: Any) -> None:
        """
        Update idle tasks in view.

        Phase 4: Convenience method for view refresh.

        Args:
            view: View object with update_idletasks method
        """
        self.update_view(view, "update_idletasks")
