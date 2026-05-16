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
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum, auto
from typing import Any, cast

import structlog

from zebtrack.ui import payloads as payloads

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
    PROJECT_IMPORT_VIDEOS = auto()
    PROJECT_PROCESS_VIDEOS = auto()
    PROJECT_GENERATE_SUMMARIES = auto()
    PROJECT_APPLY_SETTINGS = auto()
    PROJECT_DELETE_ASSET = auto()
    PROJECT_DELETE_GROUP = auto()
    PROJECT_DELETE_DAY = auto()
    PROJECT_DELETE_SUBJECT = auto()
    PROJECT_DELETE_AQUARIUM = auto()
    PROJECT_CLEAR_AQUARIUM_SUBJECT = auto()
    PROJECT_RESET_ANALYSIS_DATA = auto()
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
    # Granular default-slot management (4 method × target combinations).
    MODEL_SET_DEFAULT_FOR = auto()
    MODEL_RECLASSIFY_TARGET = auto()
    # Maintenance commands triggered from the inline weights catalog.
    MODEL_CLEAR_OPENVINO_CACHE = auto()
    MODEL_RESCAN_WEIGHTS = auto()
    MODEL_RESET_REGISTRY = auto()
    MODEL_FORCE_BENCHMARK = auto()
    MODEL_VALIDATE_WEIGHTS = auto()

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

    # ── Multi-Aquarium UI Events ──────────────────────────────────────
    UI_SHOW_AQUARIUM_COUNT_DIALOG = auto()
    UI_SHOW_AQUARIUM_ASSIGNMENT_DIALOG = auto()
    UI_UPDATE_AQUARIUM_SELECTOR = auto()
    UI_SET_AQUARIUM_SELECTOR_VISIBLE = auto()

    # ── Live Analysis ─────────────────────────────────────────────────
    UI_UPDATE_LIVE_FRAME = auto()
    LIVE_SESSION_STARTED = auto()  # Internal: coordinator after live session starts
    LIVE_SESSION_STOPPED = auto()  # Internal: coordinator after live session ends
    # Pending-session handshake (zone tab "Iniciar Gravação" button).
    LIVE_RECORDING_PENDING = auto()
    LIVE_RECORDING_RESUME_REQUESTED = auto()
    LIVE_RECORDING_CANCELLED = auto()
    # Published whenever LiveCalibrationCoordinator mutates ``_last_polygon_source``
    # (set after PreviewPolygonDialog approval, cleared after the session is
    # consumed, or tagged "manual" when the user falls back to drawing). The
    # Zone tab context panel subscribes so the badge stays in sync without polling.
    LIVE_POLYGON_SOURCE_CHANGED = auto()

    # ── Widget Internal Events (formerly raw strings) ─────────────────
    BEHAVIORAL_CONFIG_PERSPECTIVE_CHANGED = auto()
    BEHAVIORAL_CONFIG_VALUES_CHANGED = auto()
    BEHAVIORAL_CONFIG_GEOTAXIS_TOGGLED = auto()
    CONFIG_SAVE_REQUESTED = auto()
    CONFIG_VALIDATION_ERROR = auto()
    CONFIG_RESET_REQUESTED = auto()
    CONFIG_ROI_RULE_CHANGED = auto()
    CONFIG_OPEN_CALIBRATION_DIALOG = auto()
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


_PAYLOAD_TYPES: dict[UIEvents, type[Any]] = {
    # Recording
    UIEvents.RECORDING_START: payloads.RecordingStartPayload,
    UIEvents.RECORDING_STARTED: payloads.RecordingStartedPayload,
    UIEvents.RECORDING_STOP: payloads.EmptyPayload,
    UIEvents.RECORDING_TOGGLE: payloads.EmptyPayload,
    UIEvents.RECORDING_TRIGGER: payloads.RecordingTriggerPayload,
    UIEvents.RECORDING_STOPPED: payloads.RecordingStoppedPayload,
    # Project
    UIEvents.PROJECT_CREATE: payloads.ProjectCreatePayload,
    UIEvents.PROJECT_CREATED: payloads.ProjectCreatedPayload,
    UIEvents.PROJECT_OPEN: payloads.ProjectOpenPayload,
    UIEvents.PROJECT_OPENED: payloads.ProjectOpenedPayload,
    UIEvents.PROJECT_CLOSE: payloads.EmptyPayload,
    UIEvents.PROJECT_CLOSED: payloads.EmptyPayload,
    UIEvents.PROJECT_MANAGER_REPLACED: payloads.ProjectManagerReplacedPayload,
    UIEvents.PROJECT_IMPORT_VIDEOS: payloads.ProjectImportVideosPayload,
    UIEvents.PROJECT_PROCESS_VIDEOS: payloads.ProjectProcessVideosPayload,
    UIEvents.PROJECT_GENERATE_SUMMARIES: payloads.ProjectGenerateSummariesPayload,
    UIEvents.PROJECT_APPLY_SETTINGS: payloads.ProjectApplySettingsPayload,
    UIEvents.PROJECT_DELETE_ASSET: payloads.ProjectDeleteAssetPayload,
    UIEvents.PROJECT_DELETE_GROUP: payloads.ProjectDeleteGroupPayload,
    UIEvents.PROJECT_DELETE_DAY: payloads.ProjectDeleteDayPayload,
    UIEvents.PROJECT_DELETE_SUBJECT: payloads.ProjectDeleteSubjectPayload,
    UIEvents.PROJECT_DELETE_AQUARIUM: payloads.ProjectDeleteAquariumPayload,
    UIEvents.PROJECT_CLEAR_AQUARIUM_SUBJECT: payloads.ProjectClearAquariumSubjectPayload,
    UIEvents.PROJECT_RESET_ANALYSIS_DATA: payloads.ProjectResetAnalysisDataPayload,
    UIEvents.PROJECT_VIDEO_SELECTED: payloads.ProjectVideoSelectedPayload,
    UIEvents.PROJECT_SELECTION_CHANGED: payloads.ProjectSelectionChangedPayload,
    # Video Processing
    UIEvents.VIDEO_ANALYZE_SINGLE: payloads.VideoAnalyzeSinglePayload,
    UIEvents.VIDEO_START_SINGLE_PROCESSING: payloads.VideoStartSingleProcessingPayload,
    UIEvents.VIDEO_CANCEL_ANALYSIS: payloads.VideoCancelAnalysisPayload,
    # Model & Weights
    UIEvents.MODEL_SET_WEIGHT: payloads.ModelSetWeightPayload,
    UIEvents.MODEL_SET_OPENVINO: payloads.ModelSetOpenVinoPayload,
    UIEvents.MODEL_CONVERT_OPENVINO: payloads.ModelConvertOpenVinoPayload,
    UIEvents.MODEL_UPDATE_OPENVINO_STATUS: payloads.ModelUpdateOpenVinoStatusPayload,
    UIEvents.MODEL_ADD_WEIGHT: payloads.ModelAddWeightPayload,
    UIEvents.MODEL_DELETE_WEIGHT: payloads.ModelDeleteWeightPayload,
    UIEvents.MODEL_RUN_DIAGNOSTIC: payloads.ModelRunDiagnosticPayload,
    UIEvents.MODEL_LOAD_NEW_WEIGHT: payloads.ModelLoadNewWeightPayload,
    UIEvents.MODEL_SET_DEFAULT_FOR: payloads.ModelSetDefaultForPayload,
    UIEvents.MODEL_RECLASSIFY_TARGET: payloads.ModelReclassifyTargetPayload,
    UIEvents.MODEL_CLEAR_OPENVINO_CACHE: payloads.ModelClearOpenVinoCachePayload,
    UIEvents.MODEL_RESCAN_WEIGHTS: payloads.EmptyPayload,
    UIEvents.MODEL_RESET_REGISTRY: payloads.EmptyPayload,
    UIEvents.MODEL_FORCE_BENCHMARK: payloads.EmptyPayload,
    UIEvents.MODEL_VALIDATE_WEIGHTS: payloads.EmptyPayload,
    # Detector & Zone Commands
    UIEvents.DETECTOR_SETUP: payloads.DetectorSetupPayload,
    UIEvents.DETECTOR_SETUP_ZONES: payloads.DetectorSetupZonesPayload,
    UIEvents.DETECTOR_UPDATE_PARAMETERS: payloads.DetectorUpdateParametersPayload,
    UIEvents.DETECTOR_UPDATE_ZONES: payloads.DetectorUpdateZonesPayload,
    UIEvents.ZONE_SET_ARENA_POLYGON: payloads.EmptyPayload,
    UIEvents.ZONE_SAVE_MANUAL_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_UPDATE_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_AUTO_DETECT: payloads.ZoneAutoDetectPayload,
    UIEvents.ZONE_START_DRAW_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_APPLY_ROI_TEMPLATE: payloads.ZoneTemplateApplyPayload,
    UIEvents.ZONE_SAVE_ROI_TEMPLATE: payloads.EmptyPayload,
    UIEvents.ZONE_IMPORT_AND_APPLY_ROI_TEMPLATE: payloads.EmptyPayload,
    UIEvents.ZONE_RENAME_SELECTED_ROI: payloads.EmptyPayload,
    UIEvents.ZONE_CHANGE_ROI_COLOR: payloads.EmptyPayload,
    UIEvents.ZONE_REMOVE_SELECTED_ROI: payloads.EmptyPayload,
    UIEvents.ZONE_APPLY_ROI_SETTINGS: payloads.ZoneApplyRoiSettingsPayload,
    # Zone Widget Component Events
    UIEvents.ZONE_DRAW_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_DRAW_ROI: payloads.EmptyPayload,
    UIEvents.ZONE_TOGGLE_VIEW: payloads.EmptyPayload,
    UIEvents.ZONE_TEMPLATE_APPLY: payloads.ZoneTemplateApplyPayload,
    UIEvents.ZONE_TEMPLATE_SAVE: payloads.EmptyPayload,
    UIEvents.ZONE_TEMPLATE_IMPORT: payloads.EmptyPayload,
    UIEvents.ZONE_TEMPLATE_CLEAR_APPLIED: payloads.EmptyPayload,
    UIEvents.ZONE_VIDEO_SEARCH_CHANGED: payloads.ZoneVideoSearchChangedPayload,
    UIEvents.ZONE_VIDEO_REFRESH: payloads.EmptyPayload,
    UIEvents.ZONE_VIDEO_DOUBLE_CLICK: payloads.ZoneVideoDoubleClickPayload,
    UIEvents.ZONE_VIDEO_FRAME_LOAD: payloads.ZoneVideoFrameLoadPayload,
    UIEvents.ZONE_LIST_ITEM_RIGHT_CLICK: payloads.ZoneListItemRightClickPayload,
    UIEvents.ZONE_LIST_ITEM_DOUBLE_CLICK: payloads.ZoneListItemPayload,
    UIEvents.ZONE_SAVE_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_DISCARD_ARENA: payloads.EmptyPayload,
    UIEvents.ZONE_FINISH_DRAWING: payloads.EmptyPayload,
    UIEvents.ZONE_AUTO_DETECT_CLICKED: payloads.ZoneAutoDetectClickedPayload,
    UIEvents.ZONE_COPY_ZONES: payloads.VideoPathPayload,
    UIEvents.ZONE_PASTE_ZONES: payloads.VideoPathPayload,
    UIEvents.ZONE_DELETE_ZONES: payloads.VideoPathPayload,
    UIEvents.ZONE_CONCLUDE_VIDEO: payloads.EmptyPayload,
    # Multi-Aquarium
    UIEvents.ZONE_MULTI_AUTO_DETECT: payloads.ZoneMultiAutoDetectPayload,
    UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS: payloads.ZoneMultiAutoDetectSuccessPayload,
    UIEvents.ZONE_MULTI_AUTO_DETECT_FAILED: payloads.ZoneMultiAutoDetectFailedPayload,
    UIEvents.ZONE_AQUARIUM_SELECTED: payloads.ZoneAquariumSelectedPayload,
    UIEvents.ZONE_MULTI_DETECT_COMPLETED: payloads.ZoneMultiDetectCompletedPayload,
    UIEvents.ZONE_AQUARIUM_CONFIG_CONFIRMED: payloads.ZoneAquariumConfigConfirmedPayload,
    UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED: payloads.ZoneAquariumConfigUpdatedPayload,
    UIEvents.ZONE_AQUARIUM_COUNT_CONFIRMED: payloads.ZoneAquariumCountConfirmedPayload,
    UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED: payloads.ZoneAquariumAssignmentCompletedPayload,
    UIEvents.ZONE_SHOW_AQUARIUM_COUNT_DIALOG: payloads.EmptyPayload,
    UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG: payloads.ZoneShowAquariumAssignmentDialogPayload,
    UIEvents.ZONE_PROCESSING_MODE_CHANGED: payloads.ZoneProcessingModeChangedPayload,
    # Processing Reports
    UIEvents.PROCESSING_GENERATE_TRAJECTORIES: payloads.ProcessingGenerateTrajectoriesPayload,
    UIEvents.PROCESSING_EXPORT_SUMMARIES: payloads.ProcessingExportSummariesPayload,
    UIEvents.REPORTS_GENERATE_PARTIAL: payloads.ReportsGeneratePartialPayload,
    UIEvents.REPORTS_GENERATE_UNIFIED: payloads.ReportsGenerateUnifiedPayload,
    # Calibration
    UIEvents.CALIBRATION_RUN_LIVE: payloads.CalibrationRunLivePayload,
    UIEvents.CALIBRATION_COPY_TO_PROJECT: payloads.CalibrationCopyToProjectPayload,
    UIEvents.CALIBRATION_SAVE_TO_PROJECT: payloads.CalibrationSaveToProjectPayload,
    # Arduino
    UIEvents.ARDUINO_SETUP: payloads.ArduinoSetupPayload,
    UIEvents.ARDUINO_LOG_EVENT: payloads.ArduinoLogEventPayload,
    UIEvents.ARDUINO_PORT_UPDATE_REQUESTED: payloads.ArduinoPortUpdateRequestedPayload,
    # Reports / App / Wizard
    UIEvents.REPORT_GENERATE: payloads.ReportGeneratePayload,
    UIEvents.APP_CLOSE: payloads.EmptyPayload,
    UIEvents.WIZARD_CREATE_PROJECT: payloads.WizardCreateProjectPayload,
    # Controller -> UI Events
    UIEvents.UI_SHOW_ERROR: payloads.MessagePayload,
    UIEvents.UI_SHOW_WARNING: payloads.MessagePayload,
    UIEvents.UI_SHOW_INFO: payloads.MessagePayload,
    UIEvents.UI_SET_STATUS: payloads.StatusPayload,
    UIEvents.UI_UPDATE_BUTTON_STATE: payloads.UpdateButtonStatePayload,
    UIEvents.UI_REFRESH_PROJECT_VIEWS: payloads.ProjectViewsRefreshRequestedPayload,
    UIEvents.UI_UPDATE_ARDUINO_STATUS: payloads.UIUpdateArduinoStatusPayload,
    UIEvents.UI_APPEND_ARDUINO_LOG: payloads.UIAppendArduinoLogPayload,
    UIEvents.UI_UPDATE_OPENVINO_STATUS: payloads.UIUpdateOpenVinoStatusPayload,
    UIEvents.UI_SETUP_INTERACTIVE_POLYGON: payloads.SetupInteractivePolygonPayload,
    UIEvents.UI_DISPLAY_VIDEO_FRAME: payloads.VideoPathPayload,
    UIEvents.UI_UPDATE_PROCESSING_MODE: payloads.UpdateProcessingModePayload,
    UIEvents.UI_NAVIGATE_TO_WELCOME: payloads.EmptyPayload,
    UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW: payloads.EmptyPayload,
    UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW: payloads.EmptyPayload,
    UIEvents.UI_NAVIGATE_FROM_ANALYSIS_VIEW: payloads.EmptyPayload,
    UIEvents.UI_SELECT_TAB: payloads.UISelectTabPayload,
    UIEvents.UI_UPDATE_OPENVINO_CHECKBOX: payloads.UIUpdateOpenVinoCheckboxPayload,
    UIEvents.UI_SET_ACTIVE_WEIGHT: payloads.UISetActiveWeightPayload,
    UIEvents.UI_UPDATE_WEIGHTS_LIST: payloads.UIUpdateWeightsListPayload,
    UIEvents.UI_REDRAW_ZONES: payloads.ZonesUpdatedPayload,
    UIEvents.UI_UPDATE_ZONE_LIST: payloads.ZonesUpdatedPayload,
    UIEvents.UI_SHOW_EXTERNAL_TRIGGER_NOTICE: payloads.ExternalTriggerNoticePayload,
    UIEvents.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE: payloads.EmptyPayload,
    UIEvents.UI_UPDATE_ANALYSIS_METADATA: payloads.AnalysisMetadataPayload,
    UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS: payloads.AnalysisTaskStatusPayload,
    UIEvents.UI_UPDATE_DETECTION_OVERLAY: payloads.DetectionOverlayPayload,
    UIEvents.UI_DISPLAY_FRAME: payloads.FrameDisplayPayload,
    UIEvents.UI_UPDATE_SOCIAL_SUMMARY: payloads.SocialSummaryPayload,
    UIEvents.UI_UPDATE_PROCESSING_STATS: payloads.ProcessingStatsWrapperPayload,
    UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED: payloads.VideoHierarchySnapshotUpdatedPayload,
    UIEvents.UI_REQUEST_WEIGHT_FILE: payloads.UIRequestWeightFilePayload,
    UIEvents.UI_REQUEST_WEIGHT_TYPE: payloads.UIRequestWeightTypePayload,
    UIEvents.UI_REQUEST_WEIGHT_ACTION: payloads.UIRequestWeightActionPayload,
    # Multi-Aquarium UI Events
    UIEvents.UI_SHOW_AQUARIUM_COUNT_DIALOG: payloads.EmptyPayload,
    UIEvents.UI_SHOW_AQUARIUM_ASSIGNMENT_DIALOG: payloads.ZoneShowAquariumAssignmentDialogPayload,
    UIEvents.UI_UPDATE_AQUARIUM_SELECTOR: payloads.UpdateAquariumSelectorPayload,
    UIEvents.UI_SET_AQUARIUM_SELECTOR_VISIBLE: payloads.SetAquariumSelectorVisiblePayload,
    # Live Analysis
    UIEvents.UI_UPDATE_LIVE_FRAME: payloads.UIUpdateLiveFramePayload,
    UIEvents.LIVE_SESSION_STARTED: payloads.LiveSessionStartedPayload,
    UIEvents.LIVE_SESSION_STOPPED: payloads.LiveSessionStoppedPayload,
    UIEvents.LIVE_RECORDING_PENDING: payloads.LiveRecordingPendingPayload,
    UIEvents.LIVE_RECORDING_RESUME_REQUESTED: payloads.LiveRecordingResumeRequestedPayload,
    UIEvents.LIVE_RECORDING_CANCELLED: payloads.LiveRecordingCancelledPayload,
    UIEvents.LIVE_POLYGON_SOURCE_CHANGED: payloads.LivePolygonSourceChangedPayload,
    # Widget Internal Events
    UIEvents.BEHAVIORAL_CONFIG_PERSPECTIVE_CHANGED: (
        payloads.BehavioralConfigPerspectiveChangedPayload
    ),
    UIEvents.BEHAVIORAL_CONFIG_VALUES_CHANGED: payloads.BehavioralConfigValuesChangedPayload,
    UIEvents.BEHAVIORAL_CONFIG_GEOTAXIS_TOGGLED: payloads.BehavioralConfigGeotaxisToggledPayload,
    UIEvents.CONFIG_SAVE_REQUESTED: payloads.ConfigSaveRequestedPayload,
    UIEvents.CONFIG_VALIDATION_ERROR: payloads.ConfigValidationErrorPayload,
    UIEvents.CONFIG_RESET_REQUESTED: payloads.EmptyPayload,
    UIEvents.CONFIG_ROI_RULE_CHANGED: payloads.ConfigRoiRuleChangedPayload,
    UIEvents.CONFIG_OPEN_CALIBRATION_DIALOG: payloads.EmptyPayload,
    UIEvents.PROJECT_REFRESH_REQUESTED: payloads.ProjectRefreshRequestedPayload,
    UIEvents.PROJECT_VIDEO_DOUBLE_CLICK_WIDGET: payloads.ItemIdPayload,
    UIEvents.PROJECT_VIDEO_RIGHT_CLICK_WIDGET: payloads.ProjectContextMenuClickPayload,
    UIEvents.PROJECT_ITEM_DOUBLE_CLICK: payloads.ItemIdPayload,
    UIEvents.REPORTS_DELETE_UNIFIED: payloads.ReportsDeleteUnifiedPayload,
    UIEvents.CONTROL_PREVIEW_TOGGLED: payloads.ControlPreviewToggledPayload,
    UIEvents.CONTROL_INTERVAL_CHANGED: payloads.ControlIntervalChangedPayload,
    UIEvents.FRAME_ERROR: payloads.FrameErrorPayload,
    UIEvents.VIDEO_METADATA_UPDATED: payloads.VideoMetadataUpdatedPayload,
    UIEvents.ANALYSIS_TRACK_SELECTED: payloads.TrackIdPayload,
    UIEvents.ANALYSIS_CANCEL_REQUESTED: payloads.EmptyPayload,
    UIEvents.VIDEO_RECONFIGURE_SUBJECTS: payloads.VideoReconfigureSubjectsPayload,
    UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO: payloads.SetupZoneDefinitionPayload,
    # V2 Legacy
    UIEvents.ZONES_UPDATED: payloads.ZonesUpdatedPayload,
    UIEvents.ZONE_SELECTED_V2: payloads.ItemIdPayload,
    UIEvents.POLYGON_EDIT_REQUESTED: payloads.PolygonEditRequestedPayload,
    UIEvents.VIDEO_LOADED: payloads.VideoLoadedPayload,
    UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED: payloads.ProjectViewsRefreshRequestedPayload,
    UIEvents.VIDEO_TREE_REFRESH_REQUESTED: payloads.VideoTreeRefreshRequestedPayload,
    UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED: payloads.EmptyPayload,
    UIEvents.READINESS_SNAPSHOT_UPDATED: payloads.ReadinessSnapshotUpdatedPayload,
    UIEvents.PROCESSING_REPORTS_ITEM_RIGHT_CLICK: payloads.ProjectContextMenuClickPayload,
    UIEvents.UI_REQUEST_PROCESS_VIDEOS: payloads.EmptyPayload,
    UIEvents.PROCESSING_STATS_UPDATED: payloads.ProcessingStatsPayload,
    UIEvents.SOCIAL_SUMMARY_UPDATED: payloads.SocialSummaryPayload,
    UIEvents.ANALYSIS_TASK_STATUS_UPDATED: payloads.AnalysisTaskStatusPayload,
    UIEvents.SHOW_ERROR: payloads.MessagePayload,
    UIEvents.SHOW_WARNING: payloads.MessagePayload,
    UIEvents.SHOW_INFO: payloads.MessagePayload,
    UIEvents.SET_STATUS: payloads.StatusPayload,
    UIEvents.EXTERNAL_TRIGGER_NOTICE: payloads.ExternalTriggerNoticePayload,
    UIEvents.EXTERNAL_TRIGGER_NOTICE_CLEARED: payloads.EmptyPayload,
    UIEvents.ERROR_OCCURRED: payloads.ErrorOccurredPayload,
    UIEvents.PROGRESS_UPDATE: payloads.ProcessingProgressPayload,
    UIEvents.TRACKING_COMPLETE: payloads.TrackingCompletePayload,
    UIEvents.FRAME_DISPLAYED: payloads.FramePayload,
    UIEvents.ANALYSIS_STARTED: payloads.AnalysisStartedPayload,
    UIEvents.ANALYSIS_COMPLETED: payloads.AnalysisCompletedPayload,
    UIEvents.DISPLAY_VIDEO_FRAME: payloads.VideoPathPayload,
    UIEvents.NAVIGATE_TO_WELCOME: payloads.EmptyPayload,
    UIEvents.NAVIGATE_TO_PROJECT: payloads.EmptyPayload,
    UIEvents.NAVIGATE_TO_ANALYSIS: payloads.EmptyPayload,
    UIEvents.CAMERA_DISCONNECT_DETECTED: payloads.CameraDisconnectPayload,
    UIEvents.CAMERA_DISCONNECT_USER_ACTION: payloads.CameraDisconnectPayload,
    UIEvents.CAMERA_RECONNECTED: payloads.CameraDisconnectPayload,
    UIEvents.AQUARIUM_DETECTION_PROGRESS: payloads.AquariumDetectionProgressPayload,
    UIEvents.BATCH_ANALYSIS_COMPLETED: payloads.LiveBatchCompletedPayload,
    UIEvents.ZONE_DISPLAY_CLEARED: payloads.ZoneDisplayClearedPayload,
}


def _filter_payload_data(
    payload_cls: type[Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    if not is_dataclass(payload_cls):
        return data
    field_names = {field.name for field in fields(payload_cls)}
    return {key: value for key, value in data.items() if key in field_names}


def _ensure_payload_accessors(obj: payloads.EventPayload) -> payloads.EventPayload:
    if not hasattr(obj, "get"):

        def _payload_get(self, key: str, default=None):
            if hasattr(self, key):
                return getattr(self, key, default)
            if hasattr(self, "data") and isinstance(self.data, dict):
                return self.data.get(key, default)
            return default

        payload_cls = cast(Any, obj.__class__)
        payload_cls.get = _payload_get

    if not hasattr(obj, "__getitem__"):

        def _payload_getitem(self, key: str):
            if hasattr(self, key):
                return getattr(self, key)
            if hasattr(self, "data") and isinstance(self.data, dict):
                return self.data[key]
            raise KeyError(key)

        payload_cls = cast(Any, obj.__class__)
        payload_cls.__getitem__ = _payload_getitem

    return obj


def _coerce_payload(
    event_type: UIEvents,
    data: payloads.EventPayload | dict[str, Any] | None,
) -> payloads.EventPayload:
    if data is None:
        data = {}

    if is_dataclass(data):
        return _ensure_payload_accessors(data)

    if not isinstance(data, dict):
        log.warning(
            "event_bus_v2.payload.invalid_type",
            event_type=event_type.name,
            payload_type=type(data).__name__,
        )
        return payloads.UnknownPayload({"value": data})

    payload_cls = _PAYLOAD_TYPES.get(event_type)
    if payload_cls is None:
        return payloads.UnknownPayload(data)

    if isinstance(data, dict) and payload_cls is not payloads.EmptyPayload:
        log.warning(
            "event_bus_v2.payload.dict_used",
            event_type=event_type.name,
            keys=list(data.keys()),
        )

    payload_data = data
    if payload_cls is payloads.EmptyPayload:
        return payload_cls()

    filtered = _filter_payload_data(payload_cls, payload_data)
    try:
        payload_obj = payload_cls(**filtered)
    except Exception as exc:
        log.warning(
            "event_bus_v2.payload.coerce_failed",
            event_type=event_type.name,
            error=str(exc),
        )
        return payloads.UnknownPayload(data)

    return _ensure_payload_accessors(payload_obj)


@dataclass(frozen=True)
class Event:
    """Event data container.

    Attributes:
        type: The type of event (UIEvents enum).
        data: Dictionary containing event payload.
        source: Optional string identifying the event source (for debugging).
    """

    type: UIEvents
    data: payloads.EventPayload | dict[str, Any] = field(default_factory=dict)
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
        self._subscribers: dict[UIEvents, list[Callable[[payloads.EventPayload], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_type: UIEvents,
        handler: Callable[[payloads.EventPayload], None],
    ) -> None:
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

    def unsubscribe(
        self,
        event_type: UIEvents,
        handler: Callable[[payloads.EventPayload], None],
    ) -> None:
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

    def publish(
        self,
        event: UIEvents | Event,
        data: payloads.EventPayload | dict[str, Any] | None = None,
    ) -> None:
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
        handlers: list[Callable[[payloads.EventPayload], None]] = []
        if isinstance(event, Event):
            event_type = event.type
            payload = _coerce_payload(event.type, event.data)
        else:
            event_type = event
            payload = _coerce_payload(event, data)
        with self._lock:
            if event_type in self._subscribers:
                handlers = list(self._subscribers[event_type])

        if not handlers:
            return

        # ARCHITECTURAL DECISION: 100ms is FIXED threshold.
        # Slow handlers are TECH DEBT to be refactored, not edge cases to configure around.
        SLOW_HANDLER_THRESHOLD_MS = 100

        log.debug(
            "event_bus_v2.publishing",
            event_type=event_type.name,
            source=event.source if isinstance(event, Event) else None,
            subscriber_count=len(handlers),
        )

        # Execute handlers outside the lock
        # Each handler executes sequentially on the calling thread
        for handler in handlers:
            try:
                start = time.perf_counter()
                handler(payload)
                elapsed = time.perf_counter() - start
                elapsed_ms = int(elapsed * 1000)

                # v2.2: Log slow handlers as tech debt (not errors)
                if elapsed_ms > SLOW_HANDLER_THRESHOLD_MS:
                    log.warning(
                        "event_bus.slow_handler",
                        handler=handler.__name__ if hasattr(handler, "__name__") else str(handler),
                        elapsed_ms=elapsed_ms,
                        threshold_ms=SLOW_HANDLER_THRESHOLD_MS,
                        event_type=event_type.name,
                        tech_debt="Move I/O operations to background thread",
                    )
            except Exception as e:
                log.exception(
                    "event_bus_v2.handler_failed",
                    event_type=event_type.name,
                    handler=str(handler),
                    error=str(e),
                )


__all__ = [
    "Event",
    "EventBusV2",
    "UIEvents",
]
