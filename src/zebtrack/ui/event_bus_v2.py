"""Event Bus V2 implementation for Event-Driven Architecture (Track 2).

This module implements the foundation for the v4 Event-Driven Architecture,
providing a type-safe, thread-aware event bus for UI component communication.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import structlog

log = structlog.get_logger().bind(component="ui.event_bus_v2")


class UIEvents(Enum):
    """UI events for component communication.

    Includes events for:
    - Component -> GUI reverse calls (mapped from v3)
    - Service -> GUI updates
    - Inter-component communication
    """

    # Zone & ROI Management
    ZONES_UPDATED = auto()  # Replaces update_zone_listbox
    ZONE_SELECTED = auto()
    POLYGON_EDIT_REQUESTED = auto()  # Replaces setup_interactive_polygon

    # Project & Video Management
    VIDEO_LOADED = auto()
    PROJECT_VIEWS_REFRESH_REQUESTED = auto()  # Replaces refresh_project_views
    VIDEO_TREE_REFRESH_REQUESTED = auto()  # Replaces _populate_video_selector_tree
    VIDEO_HIERARCHY_SNAPSHOT_REQUESTED = auto()  # Replaces _build_video_hierarchy_snapshot
    VIDEO_HIERARCHY_SNAPSHOT_UPDATED = auto()  # New: Snapshot data ready
    READINESS_SNAPSHOT_UPDATED = auto()  # Replaces apply_pending_readiness_snapshot
    PROCESSING_REPORTS_ITEM_RIGHT_CLICK = auto()  # New: Right click context menu
    UI_REQUEST_PROCESS_VIDEOS = auto()  # Selection-aware processing trigger

    # Analysis & Processing
    PROCESSING_STATS_UPDATED = auto()  # Replaces update_processing_stats
    SOCIAL_SUMMARY_UPDATED = auto()  # Replaces update_social_summary
    ANALYSIS_TASK_STATUS_UPDATED = auto()  # Replaces update_analysis_task_status

    # Notifications & Status
    SHOW_ERROR = auto()
    SHOW_WARNING = auto()
    SHOW_INFO = auto()
    SET_STATUS = auto()

    # External Triggers / Recording
    EXTERNAL_TRIGGER_NOTICE = auto()  # Replaces show_external_trigger_notice
    EXTERNAL_TRIGGER_NOTICE_CLEARED = auto()  # Replaces clear_external_trigger_notice

    # v2.2: Video Processing Service Events (decoupling from view/root)
    ERROR_OCCURRED = auto()  # Video processing errors
    PROGRESS_UPDATE = auto()  # Processing progress updates
    TRACKING_COMPLETE = auto()  # Tracking session completed
    FRAME_DISPLAYED = auto()  # Frame ready for display

    # Analysis Lifecycle Events (added for v4 compatibility)
    ANALYSIS_STARTED = auto()  # Analysis workflow has started
    ANALYSIS_COMPLETED = auto()  # Analysis workflow has completed

    # Navigation & View State
    DISPLAY_VIDEO_FRAME = auto()
    NAVIGATE_TO_WELCOME = auto()
    NAVIGATE_TO_PROJECT = auto()
    NAVIGATE_TO_ANALYSIS = auto()

    # Live Camera Events (v2.2.0)
    CAMERA_DISCONNECT_DETECTED = auto()  # Camera disconnected during live session
    CAMERA_RECONNECTED = auto()  # Camera successfully reconnected
    AQUARIUM_DETECTION_PROGRESS = auto()  # Progress updates during aquarium detection
    BATCH_ANALYSIS_COMPLETED = auto()  # Batch analysis workflow completed

    # v2.3.2: Zone/Canvas State Management
    ZONE_DISPLAY_CLEARED = auto()  # Clear zone canvas and reset zone display state


@dataclass(frozen=True)
class Event:
    """Event data container.

    Attributes:
        type: The type of event (UIEvents enum).
        data: Dictionary containing event payload.
        source: Optional string identifying the event source (for debugging).
    """

    type: UIEvents
    data: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


class EventBusV2:
    """Centralized event bus for UI component communication.

    Thread Safety:
        - Uses threading.RLock to protect subscription state.
        - Publishing is synchronous: handlers run on the calling thread.
        - Subscribers must handle thread context switching (e.g. root.after)
          if they modify UI widgets from a background thread.
    """

    def __init__(self) -> None:
        self._subscribers: dict[UIEvents, list[Callable[[dict[str, Any]], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: UIEvents, handler: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: The UIEvents enum member to subscribe to.
            handler: Callable taking a dict payload.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                log.debug(
                    "event_bus_v2.subscribed", event_type=event_type.name, handler=str(handler)
                )

    def unsubscribe(self, event_type: UIEvents, handler: Callable[[dict[str, Any]], None]) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: The UIEvents enum member.
            handler: The handler to remove.
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    log.debug(
                        "event_bus_v2.unsubscribed",
                        event_type=event_type.name,
                        handler=str(handler),
                    )
                except ValueError:
                    log.warning(
                        "event_bus_v2.unsubscribe_failed",
                        reason="handler_not_found",
                        event_type=event_type.name,
                    )

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.

        Executes handlers synchronously. Captures exceptions in handlers
        to prevent disrupting the event flow for other subscribers.

        v2.2: Monitors handler performance with FIXED 100ms threshold.
        Slow handlers are logged as TECH DEBT to be refactored (moved to background threads).

        TODO v3.0: Rename publish() -> publish_now() for explicit synchronous semantics

        Args:
            event: The Event object to publish.
        """
        import time

        # Snapshot handlers under lock to avoid holding lock during execution
        handlers = []
        with self._lock:
            if event.type in self._subscribers:
                handlers = list(self._subscribers[event.type])

        if not handlers:
            return

        # ARCHITECTURAL DECISION: 100ms is FIXED threshold.
        # Slow handlers are TECH DEBT to be refactored, not edge cases to configure around.
        SLOW_HANDLER_THRESHOLD_MS = 100

        log.debug(
            "event_bus_v2.publishing",
            event_type=event.type.name,
            source=event.source,
            subscriber_count=len(handlers),
        )

        # Execute handlers outside the lock
        # Each handler executes sequentially on the calling thread
        for handler in handlers:
            try:
                start = time.perf_counter()
                handler(event.data)
                elapsed = time.perf_counter() - start
                elapsed_ms = int(elapsed * 1000)

                # v2.2: Log slow handlers as tech debt (not errors)
                if elapsed_ms > SLOW_HANDLER_THRESHOLD_MS:
                    log.warning(
                        "event_bus.slow_handler",
                        handler=handler.__name__ if hasattr(handler, "__name__") else str(handler),
                        elapsed_ms=elapsed_ms,
                        threshold_ms=SLOW_HANDLER_THRESHOLD_MS,
                        event_type=event.type.name,
                        tech_debt="Move I/O operations to background thread",
                    )
            except Exception as e:
                log.exception(
                    "event_bus_v2.handler_failed",
                    event_type=event.type.name,
                    handler=str(handler),
                    error=str(e),
                )
