"""
UI Scheduler Service for DRerio LogAI.

Phase 4: UI Scheduling Consolidation
Consolidates all UI scheduling and update operations into a single service,
reducing code duplication and improving testability.

This service provides:
- Thread-safe UI scheduling via root.after() or event bus
- Convenience methods for common UI operations
- Testable interface via dependency injection
- Centralized UI scheduling logic
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tkinter import Tk

log = structlog.get_logger()


class UIScheduler:
    """
    Service for scheduling UI updates and operations.

    Phase 4: Consolidates UI scheduling logic from MainViewModel,
    making UI updates testable and reducing code duplication.

    Responsibilities:
    - Schedule callbacks on UI thread
    - Provide convenience methods for common UI operations
    - Support both event bus and direct Tkinter scheduling
    - Handle errors gracefully with fallbacks

    Note: Renamed from UICoordinator to avoid collision with
    zebtrack.ui.ui_coordinator.UICoordinator (Event-Driven Mediator).
    """

    def __init__(
        self,
        root: Tk | None = None,
        event_bus: Any = None,  # Kept for backward-compat signature; ignored in v2
    ):
        """
        Initialize UIScheduler.

        Args:
            root: Tkinter root window for scheduling
            event_bus: DEPRECATED — ignored. Retained in signature for
                backward compatibility during the v1→v2 migration.
        """
        self.root = root
        self.event_bus = None  # v2: no event_bus usage
        log.info("ui_scheduler.initialized", has_root=root is not None)

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
        # v2: Always prefer root.after (no event_bus.publish_callable)
        # Try root.after
        if self.root is not None:
            try:
                self.root.after(0, lambda: func(*args, **kwargs))
                return
            except tk.TclError as e:
                log.warning(
                    "ui_scheduler.after_failed",
                    callback=getattr(func, "__name__", repr(func)),
                    error=str(e),
                )

        # Fallback to direct execution
        try:
            func(*args, **kwargs)
        # except Exception justified: arbitrary callback execution — caller errors unpredictable
        except Exception as e:
            log.error(
                "ui_scheduler.direct_execution_failed",
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
            log.warning("ui_scheduler.schedule_after_no_root")
            return None

        try:
            return self.root.after(delay_ms, lambda: func(*args, **kwargs))
        except tk.TclError as e:
            log.error(
                "ui_scheduler.schedule_after_failed",
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
        except tk.TclError as e:
            log.warning("ui_scheduler.cancel_failed", after_id=after_id, error=str(e))

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
            log.warning("ui_scheduler.update_view_no_view", method=method_name)
            return

        # Check if method exists before scheduling
        try:
            method = getattr(view, method_name, None)
            if (method is None or not callable(method)) and hasattr(
                view, "analysis_view_controller"
            ):
                controller = getattr(view, "analysis_view_controller", None)
                method = getattr(controller, method_name, None) if controller is not None else None
            if method is None or not callable(method):
                log.error(
                    "ui_scheduler.update_view_method_not_found",
                    method=method_name,
                    view_type=type(view).__name__,
                )
                return

            self.schedule(method, *args, **kwargs)
        except AttributeError:
            log.error(
                "ui_scheduler.update_view_attribute_error",
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

    def show_error(
        self, view_or_title: Any, title_or_message: str | None = None, message: str | None = None
    ) -> None:
        """Show error dialog in a view or directly via messagebox."""
        if message is None and isinstance(view_or_title, str) and title_or_message is not None:
            title = view_or_title
            try:
                from tkinter import messagebox

                messagebox.showerror(title, title_or_message)
            except tk.TclError as e:
                log.error("ui_scheduler.show_error.failed", title=title, error=str(e))
            return

        if title_or_message is None or message is None:
            log.error("ui_scheduler.show_error.invalid_args")
            return

        self.update_view(view_or_title, "show_error", title_or_message, message)

    def show_warning(
        self, view_or_title: Any, title_or_message: str | None = None, message: str | None = None
    ) -> None:
        """Show warning dialog in a view or directly via messagebox."""
        if message is None and isinstance(view_or_title, str) and title_or_message is not None:
            title = view_or_title
            try:
                from tkinter import messagebox

                messagebox.showwarning(title, title_or_message)
            except tk.TclError as e:
                log.error("ui_scheduler.show_warning.failed", title=title, error=str(e))
            return

        if title_or_message is None or message is None:
            log.error("ui_scheduler.show_warning.invalid_args")
            return

        self.update_view(view_or_title, "show_warning", title_or_message, message)

    def show_info(
        self, view_or_title: Any, title_or_message: str | None = None, message: str | None = None
    ) -> None:
        """Show info dialog in a view or directly via messagebox."""
        if message is None and isinstance(view_or_title, str) and title_or_message is not None:
            title = view_or_title
            try:
                from tkinter import messagebox

                messagebox.showinfo(title, title_or_message)
            except tk.TclError as e:
                log.error("ui_scheduler.show_info.failed", title=title, error=str(e))
            return

        if title_or_message is None or message is None:
            log.error("ui_scheduler.show_info.invalid_args")
            return

        self.update_view(view_or_title, "show_info", title_or_message, message)

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

    def ask_ok_cancel(self, title: str, message: str) -> bool:
        """
        Show OK/Cancel dialog to user.

        Args:
            title: Dialog title
            message: Dialog message

        Returns:
            True if user clicked OK, False otherwise
        """
        try:
            from tkinter import messagebox

            return messagebox.askokcancel(title, message)
        except tk.TclError as e:
            log.error(
                "ui_scheduler.ask_ok_cancel.failed",
                title=title,
                error=str(e),
            )
            # Return False as safe default (don't proceed with destructive action)
            return False
