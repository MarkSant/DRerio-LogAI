"""Event bus implementation for thread-safe UI updates in Tkinter.

Provides publish-subscribe pattern and callable event queue for coordinating
background threads with the Tkinter main thread.

.. deprecated:: v4.1
    EventBus (v1) is deprecated in favor of :class:`EventBusV2` from
    ``zebtrack.ui.event_bus_v2``. See ``docs/decisions/ADR-009-event-bus-unification.md``
    for rationale and migration plan. Removal target: v5.0.
"""

from __future__ import annotations

import queue
import warnings
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pydantic import BaseModel

log = structlog.get_logger().bind(component="ui.event_bus")


class EventType(Enum):
    """Enumerates the types of events supported by the UI event bus."""

    CALLABLE = auto()
    NAMED = auto()  # Named events with subscriber pattern


@dataclass(slots=True)
class CallableEvent:
    """Payload for executing a callable on the Tkinter main thread."""

    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def execute(self) -> None:
        """Execute the callable with stored arguments and keyword arguments."""
        self.callback(*self.args, **self.kwargs)


@dataclass(slots=True)
class NamedEvent:
    """Payload for named events with publish/subscribe pattern."""

    event_name: str
    data: Any  # Supports dict or Pydantic models


@dataclass(slots=True)
class UIEvent:
    """Unified container for UI events."""

    type: EventType
    payload: Any


class EventBus:
    """Thread-safe event bus for routing events between UI and core logic.

    Supports two modes of operation:
    1. Callable events: Direct function calls scheduled on the UI thread (legacy)
    2. Named events: Publish/subscribe pattern for decoupled communication
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Initialize the event bus.

        Args:
            maxsize: Maximum queue size (0 for unlimited).
        """
        self._queue: queue.Queue[UIEvent] = queue.Queue(maxsize=maxsize)
        # Subscribers map: event_name -> list of handlers
        self._subscribers: dict[str, list[Callable[[Any], Any]]] = defaultdict(list)

    def publish(
        self,
        event: UIEvent,
        *,
        block: bool = False,
        timeout: float | None = None,
    ) -> bool:
        """Push an event onto the queue.

        Returns True when the event was enqueued; False when the queue was full.
        """
        try:
            self._queue.put(event, block=block, timeout=timeout or 0)
            return True
        except queue.Full:
            log.warning("event_bus.publish.dropped", event_type=event.type.name)
            return False

    def publish_callable(
        self,
        callback: Callable[..., Any],
        *args: Any,
        block: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> bool:
        """Enqueue a callable event for execution.

        Convenience helper for enqueuing callable events.

        .. deprecated:: v4.1
            Use ``root.after(0, callback)`` for UI-thread scheduling, or
            ``EventBusV2.publish(Event(...))`` for event-driven communication.
        """
        warnings.warn(
            "EventBus v1 publish_callable() is DEPRECATED. "
            "Use root.after(0, callback) for UI-thread scheduling, or "
            "EventBusV2.publish(Event(UIEvents.X, data)) for event communication. "
            "See docs/decisions/ADR-009-event-bus-unification.md. "
            "Removal target: v5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        event = UIEvent(
            EventType.CALLABLE,
            CallableEvent(callback=callback, args=args, kwargs=kwargs),
        )
        published = self.publish(event, block=block, timeout=timeout)
        if not published:
            log.warning(
                "event_bus.publish_callable.failed",
                callback=getattr(callback, "__name__", repr(callback)),
            )
        return published

    def publish_event(
        self,
        event_name: str,
        data: dict[str, Any] | BaseModel | None = None,
        *,
        block: bool = False,
        timeout: float | None = None,
    ) -> bool:
        """Publish a named event with optional data payload.

        .. deprecated:: v4.1
            Use ``EventBusV2.publish(Event(UIEvents.X, data))`` instead.
            See ``docs/decisions/ADR-009-event-bus-unification.md``.

        Args:
            event_name: Name of the event (e.g., "recording:start", "project:close")
            data: Optional payload (dict or Pydantic model)
            block: Whether to block if queue is full
            timeout: Timeout for blocking operations

        Returns:
            True if event was successfully published, False if queue was full
        """
        warnings.warn(
            "EventBus v1 publish_event() is DEPRECATED. "
            "Use EventBusV2.publish(Event(UIEvents.X, data)) instead. "
            "See docs/decisions/ADR-009-event-bus-unification.md. "
            "Removal target: v5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Default to empty dict if None, otherwise use data as-is (dict or Model)
        payload = data if data is not None else {}

        event = UIEvent(
            EventType.NAMED,
            NamedEvent(event_name=event_name, data=payload),
        )
        published = self.publish(event, block=block, timeout=timeout)
        if not published:
            log.warning(
                "event_bus.publish_event.failed",
                event_name=event_name,
            )
        return published

    def subscribe(self, event_name: str, handler: Callable[[Any], Any]) -> None:
        """Subscribe a handler to a named event.

        .. deprecated:: v4.1
            Use ``EventBusV2.subscribe(UIEvents.X, handler)`` instead.
            See ``docs/decisions/ADR-009-event-bus-unification.md``.

        Args:
            event_name: Name of the event to subscribe to
            handler: Callable that accepts the event payload (dict or object)
        """
        warnings.warn(
            "EventBus v1 subscribe() is DEPRECATED. "
            "Use EventBusV2.subscribe(UIEvents.X, handler) instead. "
            "See docs/decisions/ADR-009-event-bus-unification.md. "
            "Removal target: v5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)
            log.info(
                "event_bus.subscribe",
                event_name=event_name,
                handler=getattr(handler, "__name__", repr(handler)),
            )

    def unsubscribe(self, event_name: str, handler: Callable[[Any], Any]) -> None:
        """Unsubscribe a handler from a named event.

        Args:
            event_name: Name of the event to unsubscribe from
            handler: The handler to remove
        """
        if handler in self._subscribers[event_name]:
            self._subscribers[event_name].remove(handler)
            log.info(
                "event_bus.unsubscribe",
                event_name=event_name,
                handler=getattr(handler, "__name__", repr(handler)),
            )

    def dispatch_named_event(self, event: NamedEvent) -> None:
        """Dispatch a named event to all registered subscribers.

        This should be called from the UI thread when processing named events.

        Args:
            event: The NamedEvent to dispatch
        """
        handlers = self._subscribers.get(event.event_name, [])
        log.debug(
            "event_bus.dispatch_named_event",
            event_name=event.event_name,
            num_handlers=len(handlers),
        )
        if not handlers:
            # Suppress warning for high-frequency UI events or events handled locally
            # Also suppress internal events that don't require handlers (fire-and-forget)
            if event.event_name not in (
                "ui:display_frame",
                "behavioral_config.perspective_changed",
                "behavioral_config.values_changed",
                "RECORDING_STARTED",  # Internal event - fire-and-forget
            ):
                log.warning(
                    "event_bus.dispatch.no_handlers",
                    event_name=event.event_name,
                    available_events=list(self._subscribers.keys()),
                )
            return

        for handler in handlers:
            try:
                handler(event.data)
            except Exception:
                log.exception(
                    "event_bus.dispatch.handler_failed",
                    event_name=event.event_name,
                    handler=getattr(handler, "__name__", repr(handler)),
                )

    def get_subscribers(self, event_name: str) -> list[Callable]:
        """Get list of subscribers for a given event name (for testing)."""
        return list(self._subscribers.get(event_name, []))

    def drain(self, *, max_items: int | None = None) -> list[UIEvent]:
        """Retrieve up to ``max_items`` events without blocking."""
        events: list[UIEvent] = []
        remaining = max_items if max_items is not None else -1
        while remaining != 0:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
            if remaining > 0:
                remaining -= 1
        return events

    def clear(self) -> None:
        """Remove all pending events."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def empty(self) -> bool:
        """Check if the event queue is empty.

        Returns:
            True if queue is empty, False otherwise.
        """
        return self._queue.empty()

    def size(self) -> int:
        """Return the number of events in the queue.

        Returns:
            Number of pending events.
        """
        return self._queue.qsize()


__all__ = [
    "CallableEvent",
    "EventBus",
    "EventType",
    "NamedEvent",
    "UIEvent",
]
