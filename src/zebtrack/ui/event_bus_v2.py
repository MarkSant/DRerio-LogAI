"""Unified Event Bus for ZebTrack-AI Event-Driven Architecture.

This module provides:
- ``UIEvents`` enum — the canonical set of all application events (type-safe).
- ``Event`` dataclass — immutable event payload container.
- ``EventBusV2`` — thread-safe synchronous pub/sub bus.
- ``EVENT_NAME_TO_UIEVENT`` — reverse lookup from legacy v1 string names to
  ``UIEvents`` members (used during migration; will be removed in v6.0).

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


# ── Legacy String → UIEvents Mapping ──────────────────────────────────
# Used by components still referencing the old string-based event names.
# Will be removed in v6.0 after full migration.
EVENT_NAME_TO_UIEVENT: dict[str, UIEvents] = {
    # Recording
    "recording:start": UIEvents.RECORDING_START,
    "RECORDING_STARTED": UIEvents.RECORDING_STARTED,
    "recording:stop": UIEvents.RECORDING_STOP,
    "recording:toggle": UIEvents.RECORDING_TOGGLE,
    "recording:trigger": UIEvents.RECORDING_TRIGGER,
    "RECORDING_STOPPED": UIEvents.RECORDING_STOPPED,
    # Project
    "project:create": UIEvents.PROJECT_CREATE,
    "project:created": UIEvents.PROJECT_CREATED,
    "project:open": UIEvents.PROJECT_OPEN,
    "project:opened": UIEvents.PROJECT_OPENED,
    "project:close": UIEvents.PROJECT_CLOSE,
    "project:closed": UIEvents.PROJECT_CLOSED,
    "project:manager_replaced": UIEvents.PROJECT_MANAGER_REPLACED,
    "project:process_videos": UIEvents.PROJECT_PROCESS_VIDEOS,
    "project:generate_summaries": UIEvents.PROJECT_GENERATE_SUMMARIES,
    "project:apply_settings_to_batch": UIEvents.PROJECT_APPLY_SETTINGS,
    "project:delete_asset": UIEvents.PROJECT_DELETE_ASSET,
    "project.video_selected": UIEvents.PROJECT_VIDEO_SELECTED,
    "project.selection_changed": UIEvents.PROJECT_SELECTION_CHANGED,
    "PROJECT_CREATED": UIEvents.PROJECT_CREATED,  # Raw string variant
    # Video Processing
    "video:analyze_single": UIEvents.VIDEO_ANALYZE_SINGLE,
    "video:start_single_processing": UIEvents.VIDEO_START_SINGLE_PROCESSING,
    "video:cancel_analysis": UIEvents.VIDEO_CANCEL_ANALYSIS,
    # Model & Weights
    "model:set_weight": UIEvents.MODEL_SET_WEIGHT,
    "model:set_openvino": UIEvents.MODEL_SET_OPENVINO,
    "model:convert_to_openvino": UIEvents.MODEL_CONVERT_OPENVINO,
    "model:update_openvino_status": UIEvents.MODEL_UPDATE_OPENVINO_STATUS,
    "model:add_weight": UIEvents.MODEL_ADD_WEIGHT,
    "model:delete_weight": UIEvents.MODEL_DELETE_WEIGHT,
    "model:run_diagnostic": UIEvents.MODEL_RUN_DIAGNOSTIC,
    "model:load_new_weight": UIEvents.MODEL_LOAD_NEW_WEIGHT,
    "model:manage_weights": UIEvents.MODEL_MANAGE_WEIGHTS,
    # Detector & Zones
    "detector:setup": UIEvents.DETECTOR_SETUP,
    "detector:setup_zones": UIEvents.DETECTOR_SETUP_ZONES,
    "detector:update_parameters": UIEvents.DETECTOR_UPDATE_PARAMETERS,
    "detector:update_zones": UIEvents.DETECTOR_UPDATE_ZONES,
    "zone:set_arena_polygon": UIEvents.ZONE_SET_ARENA_POLYGON,
    "zone:save_manual_arena": UIEvents.ZONE_SAVE_MANUAL_ARENA,
    "zone:update_arena": UIEvents.ZONE_UPDATE_ARENA,
    "zone:auto_detect": UIEvents.ZONE_AUTO_DETECT,
    "zone:start_draw_arena": UIEvents.ZONE_START_DRAW_ARENA,
    "zone:apply_roi_template": UIEvents.ZONE_APPLY_ROI_TEMPLATE,
    "zone:save_roi_template": UIEvents.ZONE_SAVE_ROI_TEMPLATE,
    "zone:import_and_apply_roi_template": UIEvents.ZONE_IMPORT_AND_APPLY_ROI_TEMPLATE,
    "zone:rename_selected_roi": UIEvents.ZONE_RENAME_SELECTED_ROI,
    "zone:change_roi_color": UIEvents.ZONE_CHANGE_ROI_COLOR,
    "zone:remove_selected_roi": UIEvents.ZONE_REMOVE_SELECTED_ROI,
    "zone:apply_roi_settings": UIEvents.ZONE_APPLY_ROI_SETTINGS,
    # Zone Widget Component Events
    "zone.draw_arena": UIEvents.ZONE_DRAW_ARENA,
    "zone.draw_roi": UIEvents.ZONE_DRAW_ROI,
    "zone.toggle_view": UIEvents.ZONE_TOGGLE_VIEW,
    "zone.template_apply": UIEvents.ZONE_TEMPLATE_APPLY,
    "zone.template_save": UIEvents.ZONE_TEMPLATE_SAVE,
    "zone.template_import": UIEvents.ZONE_TEMPLATE_IMPORT,
    "zone.template_clear_applied": UIEvents.ZONE_TEMPLATE_CLEAR_APPLIED,
    "zone.video_search_changed": UIEvents.ZONE_VIDEO_SEARCH_CHANGED,
    "zone.video_refresh": UIEvents.ZONE_VIDEO_REFRESH,
    "zone.video_double_click": UIEvents.ZONE_VIDEO_DOUBLE_CLICK,
    "zone.video_frame_load": UIEvents.ZONE_VIDEO_FRAME_LOAD,
    "zone.list_item_right_click": UIEvents.ZONE_LIST_ITEM_RIGHT_CLICK,
    "zone.list_item_double_click": UIEvents.ZONE_LIST_ITEM_DOUBLE_CLICK,
    "zone.save_arena": UIEvents.ZONE_SAVE_ARENA,
    "zone.discard_arena": UIEvents.ZONE_DISCARD_ARENA,
    "zone.finish_drawing": UIEvents.ZONE_FINISH_DRAWING,
    "zone.auto_detect_clicked": UIEvents.ZONE_AUTO_DETECT_CLICKED,
    "zone.copy_zones": UIEvents.ZONE_COPY_ZONES,
    "zone.paste_zones": UIEvents.ZONE_PASTE_ZONES,
    "zone.delete_zones": UIEvents.ZONE_DELETE_ZONES,
    "zone.conclude_video": UIEvents.ZONE_CONCLUDE_VIDEO,
    # Multi-Aquarium
    "zone:multi_auto_detect": UIEvents.ZONE_MULTI_AUTO_DETECT,
    "zone:multi_auto_detect_success": UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS,
    "zone:multi_auto_detect_failed": UIEvents.ZONE_MULTI_AUTO_DETECT_FAILED,
    "zone:aquarium_selected": UIEvents.ZONE_AQUARIUM_SELECTED,
    "zone:multi_detect_completed": UIEvents.ZONE_MULTI_DETECT_COMPLETED,
    "zone:aquarium_config_confirmed": UIEvents.ZONE_AQUARIUM_CONFIG_CONFIRMED,
    "zone:aquarium_config_updated": UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED,
    "zone:aquarium_count_confirmed": UIEvents.ZONE_AQUARIUM_COUNT_CONFIRMED,
    "zone:aquarium_assignment_completed": UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
    "zone:show_aquarium_count_dialog": UIEvents.ZONE_SHOW_AQUARIUM_COUNT_DIALOG,
    "zone:show_aquarium_assignment_dialog": UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
    "zone:processing_mode_changed": UIEvents.ZONE_PROCESSING_MODE_CHANGED,
    # Processing Reports
    "processing.generate_trajectories": UIEvents.PROCESSING_GENERATE_TRAJECTORIES,
    "processing.export_summaries": UIEvents.PROCESSING_EXPORT_SUMMARIES,
    "reports.generate_partial": UIEvents.REPORTS_GENERATE_PARTIAL,
    "reports.generate_unified": UIEvents.REPORTS_GENERATE_UNIFIED,
    "processing_reports.item_right_click": UIEvents.PROCESSING_REPORTS_ITEM_RIGHT_CLICK,
    # Calibration
    "calibration:run_live": UIEvents.CALIBRATION_RUN_LIVE,
    "calibration:copy_to_project": UIEvents.CALIBRATION_COPY_TO_PROJECT,
    "calibration:save_to_project": UIEvents.CALIBRATION_SAVE_TO_PROJECT,
    # Arduino
    "arduino:setup": UIEvents.ARDUINO_SETUP,
    "arduino:log_event": UIEvents.ARDUINO_LOG_EVENT,
    # Reports / App / Wizard
    "report:generate": UIEvents.REPORT_GENERATE,
    "app:close": UIEvents.APP_CLOSE,
    "wizard:create_project": UIEvents.WIZARD_CREATE_PROJECT,
    # Controller → UI
    "ui:show_error": UIEvents.UI_SHOW_ERROR,
    "ui:show_warning": UIEvents.UI_SHOW_WARNING,
    "ui:show_info": UIEvents.UI_SHOW_INFO,
    "ui:set_status": UIEvents.UI_SET_STATUS,
    "ui:update_button_state": UIEvents.UI_UPDATE_BUTTON_STATE,
    "ui:refresh_project_views": UIEvents.UI_REFRESH_PROJECT_VIEWS,
    "ui:update_arduino_status": UIEvents.UI_UPDATE_ARDUINO_STATUS,
    "ui:append_arduino_log": UIEvents.UI_APPEND_ARDUINO_LOG,
    "ui:update_openvino_status": UIEvents.UI_UPDATE_OPENVINO_STATUS,
    "ui:setup_interactive_polygon": UIEvents.UI_SETUP_INTERACTIVE_POLYGON,
    "ui:display_video_frame": UIEvents.UI_DISPLAY_VIDEO_FRAME,
    "ui:update_processing_mode": UIEvents.UI_UPDATE_PROCESSING_MODE,
    "ui:request_process_videos": UIEvents.UI_REQUEST_PROCESS_VIDEOS,
    "ui:navigate_to_welcome": UIEvents.UI_NAVIGATE_TO_WELCOME,
    "ui:navigate_to_project_view": UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW,
    "ui:navigate_to_analysis_view": UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW,
    "ui:navigate_from_analysis_view": UIEvents.UI_NAVIGATE_FROM_ANALYSIS_VIEW,
    "ui:select_tab": UIEvents.UI_SELECT_TAB,
    "ui:update_openvino_checkbox": UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
    "ui:set_active_weight": UIEvents.UI_SET_ACTIVE_WEIGHT,
    "ui:update_weights_list": UIEvents.UI_UPDATE_WEIGHTS_LIST,
    "ui:redraw_zones": UIEvents.UI_REDRAW_ZONES,
    "ui:update_zone_list": UIEvents.UI_UPDATE_ZONE_LIST,
    "ui:show_external_trigger_notice": UIEvents.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
    "ui:clear_external_trigger_notice": UIEvents.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE,
    "ui:update_analysis_metadata": UIEvents.UI_UPDATE_ANALYSIS_METADATA,
    "ui:update_analysis_task_status": UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
    "ui:update_detection_overlay": UIEvents.UI_UPDATE_DETECTION_OVERLAY,
    "ui:display_frame": UIEvents.UI_DISPLAY_FRAME,
    "ui:update_social_summary": UIEvents.UI_UPDATE_SOCIAL_SUMMARY,
    "ui:update_processing_stats": UIEvents.UI_UPDATE_PROCESSING_STATS,
    "ui:video_hierarchy_snapshot_updated": UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
    "ui:request_weight_file": UIEvents.UI_REQUEST_WEIGHT_FILE,
    "ui:request_weight_type": UIEvents.UI_REQUEST_WEIGHT_TYPE,
    "ui:request_weight_action": UIEvents.UI_REQUEST_WEIGHT_ACTION,
    "ui:open_manage_weights_dialog": UIEvents.UI_OPEN_MANAGE_WEIGHTS_DIALOG,
    # Multi-Aquarium UI
    "ui:show_aquarium_count_dialog": UIEvents.UI_SHOW_AQUARIUM_COUNT_DIALOG,
    "ui:show_aquarium_assignment_dialog": UIEvents.UI_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
    "ui:update_aquarium_selector": UIEvents.UI_UPDATE_AQUARIUM_SELECTOR,
    "ui:set_aquarium_selector_visible": UIEvents.UI_SET_AQUARIUM_SELECTOR_VISIBLE,
    # Live Analysis
    "ui:update_live_frame": UIEvents.UI_UPDATE_LIVE_FRAME,
    "LIVE_SESSION_STOPPED": UIEvents.LIVE_SESSION_STOPPED,
    # Widget Internal (raw strings)
    "behavioral_config.perspective_changed": UIEvents.BEHAVIORAL_CONFIG_PERSPECTIVE_CHANGED,
    "behavioral_config.values_changed": UIEvents.BEHAVIORAL_CONFIG_VALUES_CHANGED,
    "behavioral_config.geotaxis_toggled": UIEvents.BEHAVIORAL_CONFIG_GEOTAXIS_TOGGLED,
    "config.save_requested": UIEvents.CONFIG_SAVE_REQUESTED,
    "config.validation_error": UIEvents.CONFIG_VALIDATION_ERROR,
    "config.reset_requested": UIEvents.CONFIG_RESET_REQUESTED,
    "config.roi_rule_changed": UIEvents.CONFIG_ROI_RULE_CHANGED,
    "project.refresh_requested": UIEvents.PROJECT_REFRESH_REQUESTED,
    "project.video_double_click": UIEvents.PROJECT_VIDEO_DOUBLE_CLICK_WIDGET,
    "project.video_right_click": UIEvents.PROJECT_VIDEO_RIGHT_CLICK_WIDGET,
    "project.item_double_click": UIEvents.PROJECT_ITEM_DOUBLE_CLICK,
    "reports.delete_unified": UIEvents.REPORTS_DELETE_UNIFIED,
    "control.preview_toggled": UIEvents.CONTROL_PREVIEW_TOGGLED,
    "control.interval_changed": UIEvents.CONTROL_INTERVAL_CHANGED,
    "frame.error": UIEvents.FRAME_ERROR,
    "video.metadata_updated": UIEvents.VIDEO_METADATA_UPDATED,
    "analysis.track_selected": UIEvents.ANALYSIS_TRACK_SELECTED,
    "analysis.cancel_requested": UIEvents.ANALYSIS_CANCEL_REQUESTED,
    "video.reconfigure_subjects": UIEvents.VIDEO_RECONFIGURE_SUBJECTS,
    "ui:setup_zone_definition_for_single_video": UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO,
}


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
    "EVENT_NAME_TO_UIEVENT",
    "Event",
    "EventBusV2",
    "UIEvents",
]
