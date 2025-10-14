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
- video:cancel_analysis: {}

Model & Weight Events:
- model:set_weight: {name: str | None, dialog: Any | None}
- model:set_openvino: {use_openvino: bool, dialog: Any | None}
- model:convert_to_openvino: {dialog: Any}
- model:update_openvino_status: {dialog: Any | None}
- model:add_weight: {path: str, set_as_default: bool, weight_type: str | None}
- model:delete_weight: {name: str}
- model:run_diagnostic: {config: dict}

Detector & Zone Events:
- detector:setup: {temp_animal_method: str | None}
- detector:setup_zones: {}
- detector:update_parameters: {conf_threshold: float | None, nms_threshold: float | None,
                                track_threshold: float | None, match_threshold: float | None}
- zone:set_arena_polygon: {points: list}
- zone:save_manual_arena: {polygon_points: list[list[int]]}
- zone:update_arena: {polygon_points: list[list[int]]}

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
"""


# Event name constants for type safety and autocomplete
class Events:
    """Centralized event name constants."""

    # Recording
    RECORDING_START = "recording:start"
    RECORDING_STOP = "recording:stop"
    RECORDING_TRIGGER = "recording:trigger"

    # Project
    PROJECT_CREATE = "project:create"
    PROJECT_OPEN = "project:open"
    PROJECT_CLOSE = "project:close"
    PROJECT_PROCESS_VIDEOS = "project:process_videos"
    PROJECT_GENERATE_SUMMARIES = "project:generate_summaries"
    PROJECT_APPLY_SETTINGS = "project:apply_settings_to_batch"
    PROJECT_DELETE_ASSET = "project:delete_asset"

    # Video Processing
    VIDEO_ANALYZE_SINGLE = "video:analyze_single"
    VIDEO_CANCEL_ANALYSIS = "video:cancel_analysis"

    # Model & Weights
    MODEL_SET_WEIGHT = "model:set_weight"
    MODEL_SET_OPENVINO = "model:set_openvino"
    MODEL_CONVERT_OPENVINO = "model:convert_to_openvino"
    MODEL_UPDATE_OPENVINO_STATUS = "model:update_openvino_status"
    MODEL_ADD_WEIGHT = "model:add_weight"
    MODEL_DELETE_WEIGHT = "model:delete_weight"
    MODEL_RUN_DIAGNOSTIC = "model:run_diagnostic"

    # Detector & Zones
    DETECTOR_SETUP = "detector:setup"
    DETECTOR_SETUP_ZONES = "detector:setup_zones"
    DETECTOR_UPDATE_PARAMETERS = "detector:update_parameters"
    ZONE_SET_ARENA_POLYGON = "zone:set_arena_polygon"
    ZONE_SAVE_MANUAL_ARENA = "zone:save_manual_arena"
    ZONE_UPDATE_ARENA = "zone:update_arena"

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


__all__ = ["Events"]
