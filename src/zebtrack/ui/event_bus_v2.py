"""Unified Event Bus for ZebTrack-AI Event-Driven Architecture.

This module provides:
- ``UIEvents`` enum — the canonical set of all application events (type-safe).
- ``Event`` dataclass — immutable event payload container.
- ``EventBusV2`` — thread-safe synchronous pub/sub bus.

Phase 4 Migration (Feb 2026):
    Absorbed all ~113 ``Events`` string constants from the former ``events.py``
    and all raw-string widget events into the ``UIEvents`` enum.  The legacy
    queue-based ``EventBus`` (v1, ``event_bus.py``) and ``events.py`` have been
    deleted.  See ``docs/decisions/ADR-009-event-bus-unification.md``.
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
    """Canonical event catalog for all ZebTrack-AI communication.

    Naming convention: ``DOMAIN_ACTION`` in UPPER_SNAKE_CASE.
    Each member replaces a former ``Events.*`` string constant or a raw
    string event that was previously published via the legacy EventBus v1.
    """

    # ── Recording ─────────────────────────────────────────────────────
    RECORDING_START = auto()
    RECORDING_STARTED = auto()  # Internal fire-and-forget
    RECORDING_STOP = auto()
    RECORDING_TOGGLE = auto()
    RECORDING_TRIGGER = auto()
    RECORDING_STOPPED = auto()  # Internal: coordinator publishes after stop

    # ── Project ───────────────────────────────────────────────────────
    PROJECT_CREATE = auto()
    PROJECT_CREATED = auto()
    PROJECT_OPEN = auto()
    PROJECT_OPENED = auto()
    PROJECT_CLOSE = auto()
    PROJECT_CLOSED = auto()
    PROJECT_MANAGER_REPLACED = auto()
    PROJECT_PROCESS_VIDEOS = auto()
    PROJECT_GENERATE_SUMMARIES = auto()
    PROJECT_APPLY_SETTINGS = auto()
    PROJECT_DELETE_ASSET = auto()
    PROJECT_VIDEO_SELECTED = auto()
    PROJECT_SELECTION_CHANGED = auto()

    # ── Video Processing ──────────────────────────────────────────────
    VIDEO_ANALYZE_SINGLE = auto()
    VIDEO_START_SINGLE_PROCESSING = auto()
    VIDEO_CANCEL_ANALYSIS = auto()

    # ── Model & Weights ───────────────────────────────────────────────
    MODEL_SET_WEIGHT = auto()
    MODEL_SET_OPENVINO = auto()
    MODEL_CONVERT_OPENVINO = auto()
    MODEL_UPDATE_OPENVINO_STATUS = auto()
    MODEL_ADD_WEIGHT = auto()
    MODEL_DELETE_WEIGHT = auto()
    MODEL_RUN_DIAGNOSTIC = auto()
    MODEL_LOAD_NEW_WEIGHT = auto()
    MODEL_MANAGE_WEIGHTS = auto()

    # ── Detector & Zone Commands ──────────────────────────────────────
    DETECTOR_SETUP = auto()
    DETECTOR_SETUP_ZONES = auto()
    DETECTOR_UPDATE_PARAMETERS = auto()
    DETECTOR_UPDATE_ZONES = auto()
    ZONE_SET_ARENA_POLYGON = auto()
    ZONE_SAVE_MANUAL_ARENA = auto()
    ZONE_UPDATE_ARENA = auto()
    ZONE_AUTO_DETECT = auto()
    ZONE_START_DRAW_ARENA = auto()
    ZONE_APPLY_ROI_TEMPLATE = auto()
    ZONE_SAVE_ROI_TEMPLATE = auto()
    ZONE_IMPORT_AND_APPLY_ROI_TEMPLATE = auto()
    ZONE_RENAME_SELECTED_ROI = auto()
    ZONE_CHANGE_ROI_COLOR = auto()
    ZONE_REMOVE_SELECTED_ROI = auto()
    ZONE_APPLY_ROI_SETTINGS = auto()

    # ── Zone Widget Component Events ──────────────────────────────────
    ZONE_DRAW_ARENA = auto()
    ZONE_DRAW_ROI = auto()
    ZONE_TOGGLE_VIEW = auto()
    ZONE_TEMPLATE_APPLY = auto()
    ZONE_TEMPLATE_SAVE = auto()
    ZONE_TEMPLATE_IMPORT = auto()
    ZONE_TEMPLATE_CLEAR_APPLIED = auto()
    ZONE_VIDEO_SEARCH_CHANGED = auto()
    ZONE_VIDEO_REFRESH = auto()
    ZONE_VIDEO_DOUBLE_CLICK = auto()
    ZONE_VIDEO_FRAME_LOAD = auto()
    ZONE_LIST_ITEM_RIGHT_CLICK = auto()
    ZONE_LIST_ITEM_DOUBLE_CLICK = auto()
    ZONE_SAVE_ARENA = auto()
    ZONE_DISCARD_ARENA = auto()
    ZONE_FINISH_DRAWING = auto()
    ZONE_AUTO_DETECT_CLICKED = auto()
    ZONE_COPY_ZONES = auto()
    ZONE_PASTE_ZONES = auto()
    ZONE_DELETE_ZONES = auto()
    ZONE_CONCLUDE_VIDEO = auto()  # Raw string "zone.conclude_video"

    # ── Multi-Aquarium ────────────────────────────────────────────────
    ZONE_MULTI_AUTO_DETECT = auto()
    ZONE_MULTI_AUTO_DETECT_SUCCESS = auto()
    ZONE_MULTI_AUTO_DETECT_FAILED = auto()
    ZONE_AQUARIUM_SELECTED = auto()
    ZONE_MULTI_DETECT_COMPLETED = auto()
    ZONE_AQUARIUM_CONFIG_CONFIRMED = auto()
    ZONE_AQUARIUM_CONFIG_UPDATED = auto()
    ZONE_AQUARIUM_COUNT_CONFIRMED = auto()
    ZONE_AQUARIUM_ASSIGNMENT_COMPLETED = auto()
    ZONE_SHOW_AQUARIUM_COUNT_DIALOG = auto()
    ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG = auto()
    ZONE_PROCESSING_MODE_CHANGED = auto()

    # ── Processing Reports ────────────────────────────────────────────
    PROCESSING_GENERATE_TRAJECTORIES = auto()
    PROCESSING_EXPORT_SUMMARIES = auto()
    REPORTS_GENERATE_PARTIAL = auto()
    REPORTS_GENERATE_UNIFIED = auto()

    # ── Calibration ───────────────────────────────────────────────────
    CALIBRATION_RUN_LIVE = auto()
    CALIBRATION_COPY_TO_PROJECT = auto()
    CALIBRATION_SAVE_TO_PROJECT = auto()

    # ── Arduino ───────────────────────────────────────────────────────
    ARDUINO_SETUP = auto()
    ARDUINO_LOG_EVENT = auto()
    ARDUINO_PORT_UPDATE_REQUESTED = auto()

    # ── Reports / App / Wizard ────────────────────────────────────────
    REPORT_GENERATE = auto()
    APP_CLOSE = auto()
    WIZARD_CREATE_PROJECT = auto()

    # ── Controller → UI Events ────────────────────────────────────────
    UI_SHOW_ERROR = auto()
    UI_SHOW_WARNING = auto()
    UI_SHOW_INFO = auto()
    UI_SET_STATUS = auto()
    UI_UPDATE_BUTTON_STATE = auto()
    UI_REFRESH_PROJECT_VIEWS = auto()
    UI_UPDATE_ARDUINO_STATUS = auto()
    UI_APPEND_ARDUINO_LOG = auto()
    UI_UPDATE_OPENVINO_STATUS = auto()
    UI_SETUP_INTERACTIVE_POLYGON = auto()
    UI_DISPLAY_VIDEO_FRAME = auto()
    UI_UPDATE_PROCESSING_MODE = auto()
    UI_NAVIGATE_TO_WELCOME = auto()
    UI_NAVIGATE_TO_PROJECT_VIEW = auto()
    UI_NAVIGATE_TO_ANALYSIS_VIEW = auto()
    UI_NAVIGATE_FROM_ANALYSIS_VIEW = auto()
    UI_SELECT_TAB = auto()
    UI_UPDATE_OPENVINO_CHECKBOX = auto()
    UI_SET_ACTIVE_WEIGHT = auto()
    UI_UPDATE_WEIGHTS_LIST = auto()
    UI_REDRAW_ZONES = auto()
    UI_UPDATE_ZONE_LIST = auto()
    UI_SHOW_EXTERNAL_TRIGGER_NOTICE = auto()
    UI_CLEAR_EXTERNAL_TRIGGER_NOTICE = auto()
    UI_UPDATE_ANALYSIS_METADATA = auto()
    UI_UPDATE_ANALYSIS_TASK_STATUS = auto()
    UI_UPDATE_DETECTION_OVERLAY = auto()
    UI_DISPLAY_FRAME = auto()
    UI_UPDATE_SOCIAL_SUMMARY = auto()
    UI_UPDATE_PROCESSING_STATS = auto()
    UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED = auto()
    UI_REQUEST_WEIGHT_FILE = auto()
    UI_REQUEST_WEIGHT_TYPE = auto()
    UI_REQUEST_WEIGHT_ACTION = auto()
    UI_OPEN_MANAGE_WEIGHTS_DIALOG = auto()

    # ── Multi-Aquarium UI Events ──────────────────────────────────────
    UI_SHOW_AQUARIUM_COUNT_DIALOG = auto()
    UI_SHOW_AQUARIUM_ASSIGNMENT_DIALOG = auto()
    UI_UPDATE_AQUARIUM_SELECTOR = auto()
    UI_SET_AQUARIUM_SELECTOR_VISIBLE = auto()

    # ── Live Analysis ─────────────────────────────────────────────────
    UI_UPDATE_LIVE_FRAME = auto()
    LIVE_SESSION_STARTED = auto()  # Internal: coordinator after live session starts
    LIVE_SESSION_STOPPED = auto()  # Internal: coordinator after live session ends

    # ── Widget Internal Events (formerly raw strings) ─────────────────
    BEHAVIORAL_CONFIG_PERSPECTIVE_CHANGED = auto()
    BEHAVIORAL_CONFIG_VALUES_CHANGED = auto()
    BEHAVIORAL_CONFIG_GEOTAXIS_TOGGLED = auto()
    CONFIG_SAVE_REQUESTED = auto()
    CONFIG_VALIDATION_ERROR = auto()
    CONFIG_RESET_REQUESTED = auto()
    CONFIG_ROI_RULE_CHANGED = auto()
    PROJECT_REFRESH_REQUESTED = auto()
    PROJECT_VIDEO_DOUBLE_CLICK_WIDGET = auto()
    PROJECT_VIDEO_RIGHT_CLICK_WIDGET = auto()
    PROJECT_ITEM_DOUBLE_CLICK = auto()
    REPORTS_DELETE_UNIFIED = auto()
    CONTROL_PREVIEW_TOGGLED = auto()
    CONTROL_INTERVAL_CHANGED = auto()
    FRAME_ERROR = auto()
    VIDEO_METADATA_UPDATED = auto()
    ANALYSIS_TRACK_SELECTED = auto()
    ANALYSIS_CANCEL_REQUESTED = auto()
    VIDEO_RECONFIGURE_SUBJECTS = auto()
    SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO = auto()

    # ── V2 Legacy (kept for backward compat — already existed) ────────
    ZONES_UPDATED = auto()
    ZONE_SELECTED_V2 = auto()  # Alias for v2-specific zone selection
    POLYGON_EDIT_REQUESTED = auto()
    VIDEO_LOADED = auto()
    PROJECT_VIEWS_REFRESH_REQUESTED = auto()
    VIDEO_TREE_REFRESH_REQUESTED = auto()
    VIDEO_HIERARCHY_SNAPSHOT_REQUESTED = auto()
    READINESS_SNAPSHOT_UPDATED = auto()
    PROCESSING_REPORTS_ITEM_RIGHT_CLICK = auto()
    UI_REQUEST_PROCESS_VIDEOS = auto()
    PROCESSING_STATS_UPDATED = auto()
    SOCIAL_SUMMARY_UPDATED = auto()
    ANALYSIS_TASK_STATUS_UPDATED = auto()
    SHOW_ERROR = auto()
    SHOW_WARNING = auto()
    SHOW_INFO = auto()
    SET_STATUS = auto()
    EXTERNAL_TRIGGER_NOTICE = auto()
    EXTERNAL_TRIGGER_NOTICE_CLEARED = auto()
    ERROR_OCCURRED = auto()
    PROGRESS_UPDATE = auto()
    TRACKING_COMPLETE = auto()
    FRAME_DISPLAYED = auto()
    ANALYSIS_STARTED = auto()
    ANALYSIS_COMPLETED = auto()
    DISPLAY_VIDEO_FRAME = auto()
    NAVIGATE_TO_WELCOME = auto()
    NAVIGATE_TO_PROJECT = auto()
    NAVIGATE_TO_ANALYSIS = auto()
    CAMERA_DISCONNECT_DETECTED = auto()
    CAMERA_DISCONNECT_USER_ACTION = auto()
    CAMERA_RECONNECTED = auto()
    AQUARIUM_DETECTION_PROGRESS = auto()
    BATCH_ANALYSIS_COMPLETED = auto()
    ZONE_DISPLAY_CLEARED = auto()


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


__all__ = [
    "Event",
    "EventBusV2",
    "UIEvents",
]
