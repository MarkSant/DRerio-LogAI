"""Base widget class providing event bus integration and common functionality."""

from collections.abc import Callable
from tkinter import ttk
from typing import Any, cast

import structlog

from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

log = structlog.get_logger()


class BaseWidget(ttk.Frame):
    """
    Base class for all custom UI components.

    Provides:
    - Event bus integration for emitting user actions
    - Common widget initialization
    - Logging support
    - Consistent styling

    Subclasses should:
    - Call super().__init__() in their __init__
    - Implement _build_ui() to create their widget structure
    - Use emit_event() to notify about user actions
    """

    def __init__(self, parent: ttk.Widget, event_bus: EventBusV2 | None = None, **kwargs):
        """
        Initialize the base widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional EventBusV2 for emitting events
            **kwargs: Additional arguments passed to ttk.Frame
        """
        super().__init__(parent, **kwargs)
        self.event_bus = event_bus
        self._log = log.bind(component=self.__class__.__name__)

        # Build the UI in subclasses
        self._build_ui()

    def _build_ui(self) -> None:
        """
        Build the widget's UI structure.

        Subclasses MUST override this method to create their widgets.
        This is called automatically during __init__.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement _build_ui()")

    def emit_event(
        self,
        event_type: UIEvents,
        data: payloads.EventPayload | dict[str, Any] | None = None,
    ) -> None:
        """
        Emit a typed event to the EventBusV2.

        Args:
            event_type: UIEvents enum member.
            data: Event payload dictionary.
        """
        if self.event_bus is None:
            self._log.warning(
                "widget.event.no_bus",
                event_type=event_type.name,
                message="Event bus not configured, event not emitted",
            )
            return

        payload = data if data is not None else {}
        self.event_bus.publish(event_type, payload)
        self._log.debug(
            "widget.event.emitted",
            event_type=event_type.name,
            data_keys=list(payload.keys()) if isinstance(payload, dict) else [],
        )

    def bind_callback(
        self,
        event_type: UIEvents,
        callback: Callable[[payloads.EventPayload], None],
    ) -> None:
        """
        Subscribe to events from the event bus.

        Args:
            event_type: UIEvents enum member.
            callback: Function to call when event is received.
        """
        if self.event_bus is None:
            self._log.warning(
                "widget.subscribe.no_bus",
                event_type=event_type.name,
                message="Event bus not configured, cannot subscribe",
            )
            return

        self.event_bus.subscribe(event_type, callback)
        self._log.debug("widget.subscribed", event_type=event_type.name)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the entire widget.

        Args:
            enabled: True to enable, False to disable
        """
        state = "normal" if enabled else "disabled"
        self._set_widget_state(self, state)

    def _set_widget_state(self, widget: ttk.Widget, state: str) -> None:
        """
        Recursively set the state of all child widgets.

        Args:
            widget: Widget to modify
            state: "normal" or "disabled"
        """
        try:
            cast(Any, widget).configure(state=state)
        except Exception:
            # Some widgets don't support state configuration
            log.debug(
                "base.set_widget_state.unsupported",
                widget=type(widget).__name__,
                exc_info=True,
            )

        for child in widget.winfo_children():
            self._set_widget_state(child, state)  # type: ignore[arg-type]
