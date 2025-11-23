"""Event catalog for UI→Controller communication.

This module defines all named events used for decoupling the GUI from the Controller.
Each event name follows the pattern "domain:action" (e.g., "recording:start", "project:close").

Event Data Payloads:
-------------------

Recording Events:
- recording:start: {day: int | None, group: str | None, cobaia: str | None}
- recording:stop: {}
- recording:trigger: {event_code: int | None}

Project Events:
- project:create: {**kwargs from wizard/dialog}
- project:open: {project_path: str}
- project:close: {}
- project:process_videos: {video_paths: list[str] | None}
- project:generate_summaries: {video_paths: list[str]}
- project:apply_settings_to_batch: {videos: list}
- project:delete_asset: {video_path: str, asset: AssetType}

Video Processing Events:
- video:analyze_single: {video_path: str, config: dict}
- video:start_single_processing: {video_path: str, config: dict, zone_data: ZoneData}
- video:cancel_analysis: {}

Model & Weight Events:
- model:set_weight: {name: str | None, dialog: Any | None}
- model:set_openvino: {use_openvino: bool, dialog: Any | None}
- model:convert_to_openvino: {dialog: Any}
- model:update_openvino_status: {dialog: Any | None}
- model:add_weight: {path: str, set_as_default: bool, weight_type: str | None}
- model:delete_weight: {name: str}
- model:run_diagnostic: {config: dict}
- model:load_new_weight: {}
- model:manage_weights: {}

Detector & Zone Events:
- detector:setup: {temp_animal_method: str | None}
- detector:setup_zones: {}
- detector:update_parameters: {conf_threshold: float | None, nms_threshold: float | None,
                                track_threshold: float | None, match_threshold: float | None}
- zone:set_arena_polygon: {points: list}
- zone:save_manual_arena: {polygon_points: list[list[int]]}
- zone:update_arena: {polygon_points: list[list[int]]}
- zone:auto_detect: {stabilization_frames: int}

Calibration Events:
- calibration:run_live: {temp_aquarium_method: str | None}
- calibration:copy_to_project: {}
- calibration:save_to_project: {}

Arduino Events:
- arduino:setup: {}
- arduino:log_event: {message: str}

Report Events:
- report:generate: {videos: list[dict], report_type: str}

Application Events:
- app:close: {}
- wizard:create_project: {**kwargs}
- project:open: {project_path: str}

Controller→UI Events (New in Phase 1 Refactoring):
-------------------
These events are published by the MainViewModel and consumed by the ApplicationGUI
or its components to decouple the view model from the view.

- ui:show_error: {title: str, message: str}
- ui:show_warning: {title: str, message: str}
- ui:show_info: {title: str, message: str}
- ui:set_status: {message: str}
- ui:update_button_state: {button_name: str, state: str}
- ui:refresh_project_views: {reason: str, append_summary: bool, immediate: bool}
- ui:update_arduino_status: {connected: bool, port: str | None}
- ui:append_arduino_log: {message: str}
- ui:update_openvino_status: {status: str}
- ui:setup_interactive_polygon: {polygon: list}
- ui:display_video_frame: {video_path: str}
- ui:update_processing_mode: {report: Any} # ProcessingReport
- ui:navigate_to_welcome: {}
- ui:navigate_to_project_view: {}
- ui:navigate_to_analysis_view: {}
- ui:navigate_from_analysis_view: {}
- ui:update_openvino_checkbox: {is_checked: bool}
- ui:set_active_weight: {weight_name: str}
- ui:update_weights_list: {weights: list[str]}
- ui:redraw_zones: {}
- ui:update_zone_list: {}
- ui:select_tab: {tab_name: str} # e.g., "zone_tab"
- ui:show_external_trigger_notice: {context: dict}
- ui:clear_external_trigger_notice: {}
- ui:update_analysis_metadata: {metadata: dict}
- ui:update_analysis_task_status: {payload: dict}
- ui:update_detection_overlay: {detections: list, report: Any}
- ui:display_frame: {frame: Any} # numpy array
- ui:update_social_summary: {summary: dict}
- ui:update_processing_stats: {stats: dict}
"""


# Event name constants for type safety and autocomplete
class Events:
    """Centralized event name constants."""

    # Recording
    RECORDING_START = "recording:start"
    RECORDING_STOP = "recording:stop"
    RECORDING_TOGGLE = "recording:toggle"
    RECORDING_TRIGGER = "recording:trigger"

    # Project
    PROJECT_CREATE = "project:create"
    PROJECT_OPEN = "project:open"
    PROJECT_CLOSE = "project:close"
    PROJECT_PROCESS_VIDEOS = "project:process_videos"
    PROJECT_ADD_VIDEOS = "project:add_videos"
    PROJECT_GENERATE_SUMMARIES = "project:generate_summaries"
    PROJECT_APPLY_SETTINGS = "project:apply_settings_to_batch"
    PROJECT_DELETE_ASSET = "project:delete_asset"

    # Video Processing
    VIDEO_ANALYZE_SINGLE = "video:analyze_single"
    VIDEO_START_SINGLE_PROCESSING = "video:start_single_processing"
    VIDEO_CANCEL_ANALYSIS = "video:cancel_analysis"

    # Model & Weights
    MODEL_SET_WEIGHT = "model:set_weight"
    MODEL_SET_OPENVINO = "model:set_openvino"
    MODEL_CONVERT_OPENVINO = "model:convert_to_openvino"
    MODEL_UPDATE_OPENVINO_STATUS = "model:update_openvino_status"
    MODEL_ADD_WEIGHT = "model:add_weight"
    MODEL_DELETE_WEIGHT = "model:delete_weight"
    MODEL_RUN_DIAGNOSTIC = "model:run_diagnostic"
    MODEL_LOAD_NEW_WEIGHT = "model:load_new_weight"
    MODEL_MANAGE_WEIGHTS = "model:manage_weights"

    # Detector & Zones
    DETECTOR_SETUP = "detector:setup"
    DETECTOR_SETUP_ZONES = "detector:setup_zones"
    DETECTOR_UPDATE_PARAMETERS = "detector:update_parameters"
    ZONE_SET_ARENA_POLYGON = "zone:set_arena_polygon"
    ZONE_SAVE_MANUAL_ARENA = "zone:save_manual_arena"
    ZONE_UPDATE_ARENA = "zone:update_arena"
    ZONE_AUTO_DETECT = "zone:auto_detect"
    ZONE_START_DRAW_ARENA = "zone:start_draw_arena"
    ZONE_APPLY_ROI_TEMPLATE = "zone:apply_roi_template"
    ZONE_SAVE_ROI_TEMPLATE = "zone:save_roi_template"
    ZONE_IMPORT_AND_APPLY_ROI_TEMPLATE = "zone:import_and_apply_roi_template"
    ZONE_RENAME_SELECTED_ROI = "zone:rename_selected_roi"
    ZONE_CHANGE_ROI_COLOR = "zone:change_roi_color"
    ZONE_REMOVE_SELECTED_ROI = "zone:remove_selected_roi"
    ZONE_APPLY_ROI_SETTINGS = "zone:apply_roi_settings"

    # ZoneControlsWidget events (Component specific)
    ZONE_DRAW_ARENA = "zone.draw_arena"
    ZONE_DRAW_ROI = "zone.draw_roi"
    ZONE_TOGGLE_VIEW = "zone.toggle_view"
    ZONE_TEMPLATE_APPLY = "zone.template_apply"
    ZONE_TEMPLATE_SAVE = "zone.template_save"
    ZONE_TEMPLATE_IMPORT = "zone.template_import"
    ZONE_VIDEO_SEARCH_CHANGED = "zone.video_search_changed"
    ZONE_VIDEO_REFRESH = "zone.video_refresh"
    ZONE_VIDEO_DOUBLE_CLICK = "zone.video_double_click"
    ZONE_VIDEO_FRAME_LOAD = "zone.video_frame_load"
    ZONE_LIST_ITEM_RIGHT_CLICK = "zone.list_item_right_click"
    ZONE_LIST_ITEM_DOUBLE_CLICK = "zone.list_item_double_click"
    ZONE_SAVE_ARENA = "zone.save_arena"
    ZONE_DISCARD_ARENA = "zone.discard_arena"
    ZONE_AUTO_DETECT_CLICKED = "zone.auto_detect_clicked"

    # Calibration
    CALIBRATION_RUN_LIVE = "calibration:run_live"
    CALIBRATION_COPY_TO_PROJECT = "calibration:copy_to_project"
    CALIBRATION_SAVE_TO_PROJECT = "calibration:save_to_project"

    # Arduino
    ARDUINO_SETUP = "arduino:setup"
    ARDUINO_LOG_EVENT = "arduino:log_event"

    # Reports
    REPORT_GENERATE = "report:generate"

    # Application
    APP_CLOSE = "app:close"

    # Wizard
    WIZARD_CREATE_PROJECT = "wizard:create_project"

    # Project
    PROJECT_OPEN = "project:open"

    # --------------------------------------------------------------------------
    # Controller -> UI Events
    # --------------------------------------------------------------------------
    UI_SHOW_ERROR = "ui:show_error"
    UI_SHOW_WARNING = "ui:show_warning"
    UI_SHOW_INFO = "ui:show_info"
    UI_SET_STATUS = "ui:set_status"
    UI_UPDATE_BUTTON_STATE = "ui:update_button_state"
    UI_REFRESH_PROJECT_VIEWS = "ui:refresh_project_views"
    UI_UPDATE_ARDUINO_STATUS = "ui:update_arduino_status"
    UI_APPEND_ARDUINO_LOG = "ui:append_arduino_log"
    UI_UPDATE_OPENVINO_STATUS = "ui:update_openvino_status"
    UI_SETUP_INTERACTIVE_POLYGON = "ui:setup_interactive_polygon"
    UI_DISPLAY_VIDEO_FRAME = "ui:display_video_frame"
    UI_UPDATE_PROCESSING_MODE = "ui:update_processing_mode"

    # Navigation
    UI_NAVIGATE_TO_WELCOME = "ui:navigate_to_welcome"
    UI_NAVIGATE_TO_PROJECT_VIEW = "ui:navigate_to_project_view"
    UI_NAVIGATE_TO_ANALYSIS_VIEW = "ui:navigate_to_analysis_view"
    UI_NAVIGATE_FROM_ANALYSIS_VIEW = "ui:navigate_from_analysis_view"
    UI_SELECT_TAB = "ui:select_tab"

    # Widget updates
    UI_UPDATE_OPENVINO_CHECKBOX = "ui:update_openvino_checkbox"
    UI_SET_ACTIVE_WEIGHT = "ui:set_active_weight"
    UI_UPDATE_WEIGHTS_LIST = "ui:update_weights_list"
    UI_REDRAW_ZONES = "ui:redraw_zones"
    UI_UPDATE_ZONE_LIST = "ui:update_zone_list"

    # Recording/Triggering
    UI_SHOW_EXTERNAL_TRIGGER_NOTICE = "ui:show_external_trigger_notice"
    UI_CLEAR_EXTERNAL_TRIGGER_NOTICE = "ui:clear_external_trigger_notice"

    # Analysis/Processing View
    UI_UPDATE_ANALYSIS_METADATA = "ui:update_analysis_metadata"
    UI_UPDATE_ANALYSIS_TASK_STATUS = "ui:update_analysis_task_status"
    UI_UPDATE_DETECTION_OVERLAY = "ui:update_detection_overlay"
    UI_DISPLAY_FRAME = "ui:display_frame"
    UI_UPDATE_SOCIAL_SUMMARY = "ui:update_social_summary"
    UI_UPDATE_PROCESSING_STATS = "ui:update_processing_stats"
    UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED = "ui:video_hierarchy_snapshot_updated"

    # Weight Management
    UI_REQUEST_WEIGHT_FILE = "ui:request_weight_file"
    UI_REQUEST_WEIGHT_TYPE = "ui:request_weight_type"
    UI_REQUEST_WEIGHT_ACTION = "ui:request_weight_action"
    UI_OPEN_MANAGE_WEIGHTS_DIALOG = "ui:open_manage_weights_dialog"


__all__ = ["Events"]
