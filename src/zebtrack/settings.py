"""
This module defines the Pydantic models for application settings and provides
a loader function to read and validate the configuration from a YAML file.
"""

from pathlib import Path
from typing import List, Literal, Tuple

import structlog
import yaml
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

log = structlog.get_logger()


# --- Pydantic Models for Configuration Structure ---


class CameraSettings(BaseModel):
    """Settings related to the camera source."""

    index: int = Field(..., description="The index of the camera device (e.g., 0, 1).")
    desired_width: int = Field(
        ..., description="The width (pixels) used for defining detection zones."
    )
    desired_height: int = Field(
        ..., description="The height (pixels) used for defining detection zones."
    )


class ArduinoSettings(BaseModel):
    """Settings for connecting to an Arduino device."""

    port: str = Field(
        ...,
        description=(
            "The serial port the Arduino is connected to (e.g., 'COM5' or "
            "'/dev/ttyACM0')."
        ),
    )
    baud_rate: int = Field(..., description="The baud rate for serial communication.")


class RecorderSettings(BaseModel):
    """Settings for Parquet/video recorder behavior."""

    flush_interval_seconds: float = Field(
        5.0,
        ge=0.0,
        description="Interval between automatic flushes of detection data to disk.",
    )
    flush_row_threshold: int = Field(
        500,
        ge=1,
        description="Number of detection rows buffered before forcing a flush.",
    )


class YOLOModelSettings(BaseModel):
    """Settings for the YOLO object detection model."""

    path: str = Field(
        ..., description="Path to the YOLO model weights file (e.g., 'model.pt')."
    )
    confidence_threshold: float = Field(
        ...,
        gt=0,
        lt=1,
        description="Minimum confidence score for a detection to be considered valid.",
    )
    nms_threshold: float = Field(
        ...,
        gt=0,
        lt=1,
        description=(
            "Non-Maximum Suppression threshold for filtering overlapping bounding "
            "boxes."
        ),
    )


class ByteTrackSettings(BaseModel):
    """Association thresholds for the ByteTrack tracker."""

    track_threshold: float = Field(
        0.25,
        gt=0,
        lt=1,
        description=(
            "Minimum score required to keep a detection associated with an existing "
            "track during the ByteTrack matching stage."
        ),
    )
    match_threshold: float = Field(
        0.15,
        gt=0,
        lt=1,
        description=(
            "Threshold used when linking unmatched detections to existing tracks in "
            "ByteTrack's second association pass."
        ),
    )


class VideoProcessingSettings(BaseModel):
    """Settings for processing video files or live streams."""

    fps: int = Field(
        ..., description="Frames Per Second (FPS) for saving output videos."
    )
    processing_interval: int = Field(
        ..., description="Process 1 frame every N frames to optimize performance."
    )
    processing_offset: int = Field(
        ...,
        description=(
            "Frame offset for processing. E.g., offset=1 and interval=10 processes "
            "frames 1, 11, 21, ..."
        ),
    )
    sharp_turn_threshold_deg_s: float = 200.0
    freezing_velocity_threshold: float = 1.5
    freezing_min_duration_s: float = 1.0
    # Single animal tracking mode
    single_animal_per_aquarium: bool = Field(
        False,
        description="When True, forces consistent track_id=1 for single animal "
        "scenarios.",
    )


class TrajectorySmoothingSettings(BaseModel):
    """Smoothing parameters applied to trajectory preprocessing."""

    window_length: int = Field(
        7,
        ge=3,
        description=(
            "Odd-sized window used by the Savitzky-Golay filter during trajectory "
            "smoothing."
        ),
    )
    polyorder: int = Field(
        3,
        ge=1,
        description=(
            "Polynomial order for the Savitzky-Golay filter. Must be strictly "
            "less than the window length."
        ),
    )

    @field_validator("window_length")
    @classmethod
    def _ensure_odd_window(cls, value: int) -> int:
        if value % 2 == 0:
            raise ValueError(
                "trajectory_smoothing.window_length must be an odd integer."
            )
        return value

    @model_validator(mode="after")
    def _validate_polyorder(self) -> "TrajectorySmoothingSettings":
        if self.polyorder >= self.window_length:
            raise ValueError(
                "trajectory_smoothing.polyorder must be less than window_length."
            )
        return self


class AngularVelocitySettings(BaseModel):
    """Parameters for robust angular velocity calculation."""

    min_displacement_threshold_cm: float = Field(
        0.5,
        ge=0.0,
        description=(
            "Minimum displacement (in cm) required between consecutive positions "
            "to calculate a valid angular velocity. When displacement is below this "
            "threshold, the animal is considered stationary and angular velocity is "
            "set to NaN. This prevents noise amplification from detector jitter when "
            "the subject is nearly stationary. Typical values: 0.3-1.0 cm."
        ),
    )
    angle_calculation_window: int = Field(
        1,
        ge=1,
        description=(
            "Frame step for angle calculation. A value of 1 calculates angles between "
            "consecutive frames (F-1, F, F+1). Higher values (e.g., 3) use frames "
            "(F-3, F, F+3), creating longer displacement vectors that are more robust "
            "to detection noise but reduce temporal resolution. Use values 2-5 for "
            "noisy detections."
        ),
    )
    angular_velocity_smoothing_window: int = Field(
        3,
        ge=1,
        description=(
            "Window size for optional moving average smoothing of calculated angular "
            "velocities. A value of 1 disables smoothing. Values of 3-5 reduce "
            "high-frequency noise in angular velocity time series without over-"
            "smoothing genuine rapid turns."
        ),
    )

    @field_validator("angular_velocity_smoothing_window")
    @classmethod
    def _ensure_odd_smoothing_window(cls, value: int) -> int:
        if value > 1 and value % 2 == 0:
            raise ValueError(
                "angular_velocity.angular_velocity_smoothing_window must be odd or "
                "equal to 1."
            )
        return value


class TrackingSettings(BaseModel):
    """Toggle options that affect tracker selection and behavior."""

    use_single_subject_tracker: bool = Field(
        False,
        description=(
            "When True, prefer the lightweight single-subject tracker instead of "
            "ByteTrack for single-animal experiments."
        ),
    )


class DetectionZonesSettings(BaseModel):
    """Defines the coordinates for areas of interest in the camera frame."""

    polygon: List[List[int]] = Field(
        default_factory=list,
        description="A list of [x, y] points defining the main detection polygon.",
    )
    roi_polygons: List[List[List[int]]] = Field(
        default_factory=list,
        description="A list of polygons, where each polygon is a list of [x,y] points.",
    )
    roi_names: List[str] = Field(
        default_factory=list,
        description="The names for each ROI polygon.",
    )
    roi_colors: List[Tuple[int, int, int]] = Field(
        default_factory=list,
        description="The BGR colors for drawing each ROI polygon on the overlay.",
    )


class ReproducibilitySettings(BaseModel):
    """Settings related to ensuring reproducible results."""

    seed: int = Field(
        42,
        description=(
            "Seed for random number generators (numpy, torch) to ensure consistent "
            "results."
        ),
    )


class ModelSelectionSettings(BaseModel):
    """Settings for selecting which model type to use for different tasks."""

    aquarium_method: Literal["seg", "det"] = Field(
        "seg",
        description=(
            "Method for aquarium detection: 'seg' for segmentation, 'det' for "
            "detection"
        ),
    )
    animal_method: Literal["seg", "det"] = Field(
        "det",
        description=(
            "Method for animal tracking: 'seg' for segmentation, 'det' for "
            "detection"
        ),
    )
    use_openvino: bool = Field(
        False,
        description="Whether to use OpenVINO for model inference",
    )


class WeightsSelectionSettings(BaseModel):
    """Settings for weight file selection by type."""

    seg_filename: str = Field(
        "best_seg.pt",
        description="Filename for segmentation model weights",
    )
    det_filename: str = Field(
        "best_oi.pt",
        description="Filename for detection model weights",
    )


class UIFeatureFlags(BaseModel):
    """Feature flags for UI/UX experiments and gradual rollouts."""

    use_wizard_for_project_creation: bool = Field(
        False,
        description="Use new 5-step wizard instead of legacy CreateProjectDialog"
    )
    enable_event_queue: bool = Field(
        False,
        description=(
            "Route controller→GUI interactions through the async event queue "
            "instead of direct Tkinter calls"
        ),
    )


class Settings(BaseModel):
    """Main settings model that nests all other configuration sections."""

    camera: CameraSettings
    arduino: ArduinoSettings
    recorder: RecorderSettings = Field(
        default_factory=RecorderSettings,  # type: ignore[arg-type]
        description="Settings for Parquet/video recorder behavior",
    )
    yolo_model: YOLOModelSettings
    bytetrack: ByteTrackSettings = Field(
        default_factory=ByteTrackSettings,  # type: ignore[arg-type]
        description="Default thresholds used by the ByteTrack tracker.",
    )
    video_processing: VideoProcessingSettings
    tracking: TrackingSettings = Field(
        default_factory=TrackingSettings,  # type: ignore[arg-type]
        description="Tracker selection toggles and preferences.",
    )
    detection_zones: DetectionZonesSettings = Field(
        default_factory=DetectionZonesSettings
    )
    reproducibility: ReproducibilitySettings

    # New dual-weight selection settings
    model_selection: ModelSelectionSettings = Field(
        default_factory=ModelSelectionSettings,  # type: ignore[arg-type]
        description="Settings for selecting model types (seg/det) for different tasks",
    )
    weights: WeightsSelectionSettings = Field(
        default_factory=WeightsSelectionSettings,  # type: ignore[arg-type]
        description="Settings for weight file selection by type",
    )

    # ROI inclusion rule settings
    roi_inclusion_rule: Literal[
        "centroid_in",
        "centroid_in_on_buffered_roi",
        "bbox_intersects",
        "seg_overlap",
    ] = "bbox_intersects"
    roi_buffer_radius_value: float = 0.5
    roi_min_bbox_overlap_ratio: float = 0.10

    # UI Feature Flags
    ui_features: UIFeatureFlags = Field(
        default_factory=UIFeatureFlags,  # type: ignore[arg-type]
        description="Feature flags for UI experiments and gradual rollouts"
    )
    trajectory_smoothing: TrajectorySmoothingSettings = Field(
        default_factory=TrajectorySmoothingSettings,  # type: ignore[arg-type]
        description="Smoothing parameters applied to trajectory preprocessing.",
    )
    angular_velocity: AngularVelocitySettings = Field(
        default_factory=AngularVelocitySettings,  # type: ignore[arg-type]
        description=(
            "Parameters for robust angular velocity calculation to handle "
            "detection jitter."
        ),
    )

    @model_validator(mode="after")
    def _validate_advanced_constraints(self) -> "Settings":
        """Ensure cross-field invariants that depend on multiple settings."""

        # Validate processing interval/offset relationship
        interval = self.video_processing.processing_interval
        offset = self.video_processing.processing_offset
        if interval <= 0:
            raise ValueError(
                "video_processing.processing_interval must be a positive integer."
            )
        if offset < 0:
            raise ValueError(
                "video_processing.processing_offset must be greater than or equal to 0."
            )
        if offset >= interval:
            raise ValueError(
                "video_processing.processing_offset must be less than "
                "processing_interval."
            )

        # Validate ROI parameters based on rule selection
        if self.roi_inclusion_rule == "centroid_in_on_buffered_roi":
            if self.roi_buffer_radius_value <= 0:
                raise ValueError(
                    "roi_buffer_radius_value must be greater than 0 when using "
                    "centroid_in_on_buffered_roi."
                )
        elif self.roi_buffer_radius_value < 0:
            raise ValueError("roi_buffer_radius_value cannot be negative.")

        overlap_ratio = self.roi_min_bbox_overlap_ratio
        if self.roi_inclusion_rule in {"bbox_intersects", "seg_overlap"}:
            if not (0.0 < overlap_ratio <= 1.0):
                raise ValueError(
                    "roi_min_bbox_overlap_ratio must be within (0, 1] when using "
                    "bbox_intersects or seg_overlap."
                )
        else:
            if not (0.0 <= overlap_ratio <= 1.0):
                raise ValueError(
                    "roi_min_bbox_overlap_ratio must be within [0, 1] for the "
                    "selected ROI inclusion rule."
                )

        return self


def _merge_configs(base: dict, override: dict) -> dict:
    """Recursively merge two dictionaries."""
    for key, value in override.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            base[key] = _merge_configs(base[key], value)
        else:
            base[key] = value
    return base


def load_settings(
    default_config_path: Path = Path("config.yaml"),
    override_config_path: Path = Path("config.local.yaml"),
) -> Settings:
    """
    Loads settings from YAML files, validates them, and returns a Settings object.

    This function implements a hierarchical configuration system:
    1. It loads the base configuration from `default_config_path`.
    2. If `override_config_path` exists, it loads it and recursively merges its
       values on top of the base configuration. This allows users to maintain
       local settings (e.g., camera index) without modifying the main config file.

    Args:
        default_config_path (Path): The path to the base configuration file.
        override_config_path (Path): The path to the local override file.

    Returns:
        Settings: A validated Pydantic settings object.

    Raises:
        FileNotFoundError: If the default config file does not exist.
        ValueError: If there are validation or parsing errors.
    """
    if not default_config_path.is_file():
        log.error("settings.load.file_not_found", path=str(default_config_path))
        raise FileNotFoundError(
            f"Default configuration file not found at: {default_config_path}"
        )

    log.info("settings.load.start", path=str(default_config_path))
    try:
        with open(default_config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if override_config_path.is_file():
            log.info("settings.load.override", path=str(override_config_path))
            with open(override_config_path, "r", encoding="utf-8") as f:
                override_data = yaml.safe_load(f)
            if override_data:
                config_data = _merge_configs(config_data, override_data)

        settings = Settings.model_validate(config_data)
        log.info("settings.load.success")
        return settings
    except yaml.YAMLError as e:
        log.error("settings.load.yaml_error", error=str(e))
        raise ValueError(f"Error parsing YAML file: {e}")
    except ValidationError as e:
        log.error("settings.load.validation_error", error=str(e))
        raise ValueError(f"Configuration validation error: {e}")


# Load settings once on module import to be used across the application
try:
    settings = load_settings()
except (FileNotFoundError, ValueError) as e:
    log.critical("settings.load.failed", error=str(e))
    # In a real app, you might want to exit or use default settings
    settings = None
