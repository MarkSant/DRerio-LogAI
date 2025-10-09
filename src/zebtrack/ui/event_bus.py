from __future__ import annotations

import queue
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, List, Optional

import structlog

log = structlog.get_logger().bind(component="ui.event_bus")


class EventType(Enum):
    """Enumerates the types of events supported by the UI event bus."""

    CALLABLE = auto()


@dataclass(slots=True)
class CallableEvent:
    """Payload for executing a callable on the Tkinter main thread."""

    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def execute(self) -> None:
        self.callback(*self.args, **self.kwargs)


@dataclass(slots=True)
class UIEvent:
    """Unified container for UI events."""

    type: EventType
    payload: Any


class EventBus:
    """Thread-safe queue for routing controller events to the GUI thread."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[UIEvent] = queue.Queue(maxsize=maxsize)

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

    def drain(self, *, max_items: Optional[int] = None) -> List[UIEvent]:
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
    "UIEvent",
]
