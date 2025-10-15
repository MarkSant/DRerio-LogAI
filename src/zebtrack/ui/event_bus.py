from __future__ import annotations

import queue
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable

import structlog

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
        self.callback(*self.args, **self.kwargs)


@dataclass(slots=True)
class NamedEvent:
    """Payload for named events with publish/subscribe pattern."""

    event_name: str
    data: dict[str, Any]


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
        self._queue: queue.Queue[UIEvent] = queue.Queue(maxsize=maxsize)
        # Subscribers map: event_name -> list of handlers
        self._subscribers: dict[str, list[Callable[[dict], Any]]] = defaultdict(list)

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
        """Convenience helper for enqueuing callable events."""

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
        data: dict[str, Any] | None = None,
        *,
        block: bool = False,
        timeout: float | None = None,
    ) -> bool:
        """Publish a named event with optional data payload.

        Args:
            event_name: Name of the event (e.g., "recording:start", "project:close")
            data: Optional dictionary containing event-specific data
            block: Whether to block if queue is full
            timeout: Timeout for blocking operations

        Returns:
            True if event was successfully published, False if queue was full
        """
        event = UIEvent(
            EventType.NAMED,
            NamedEvent(event_name=event_name, data=data or {}),
        )
        published = self.publish(event, block=block, timeout=timeout)
        if not published:
            log.warning(
                "event_bus.publish_event.failed",
                event_name=event_name,
            )
        return published

    def subscribe(self, event_name: str, handler: Callable[[dict], Any]) -> None:
        """Subscribe a handler to a named event.

        Args:
            event_name: Name of the event to subscribe to
            handler: Callable that accepts a dict of event data
        """
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)
            log.info(
                "event_bus.subscribe",
                event_name=event_name,
                handler=getattr(handler, "__name__", repr(handler)),
            )

    def unsubscribe(self, event_name: str, handler: Callable[[dict], Any]) -> None:
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
        if not handlers:
            log.warning(
                "event_bus.dispatch.no_handlers",
                event_name=event.event_name,
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
        return self._queue.empty()

    def size(self) -> int:
        return self._queue.qsize()


__all__ = [
    "CallableEvent",
    "EventBus",
    "EventType",
    "NamedEvent",
    "UIEvent",
]
