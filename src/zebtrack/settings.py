"""
This module defines the Pydantic models for application settings and provides
a loader function to read and validate the configuration from a YAML file.

The settings system uses a hierarchical configuration approach:
1. Base configuration loaded from config.yaml
2. Optional overrides from config.local.yaml (git-ignored for local customization)
3. Pydantic v2 validation ensures type safety and business rule compliance

Usage (Dependency Injection):
    from zebtrack.settings import load_settings, Settings

    # Load settings once in main composition root
    settings_obj = load_settings()

    # Inject into classes that need configuration
    manager = WeightManager(settings_obj=settings_obj)
    service = AnalysisService(settings_obj=settings_obj)

    # Access configuration values from injected instance
    camera_index = settings_obj.camera.index
    confidence = settings_obj.yolo_model.confidence_threshold

    # Reload settings at runtime (useful for config editor)
    from zebtrack.settings import reload_settings
    new_settings = reload_settings()

    # Export JSON schema for documentation
    from zebtrack.settings import export_schema
    schema = export_schema()
"""

from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

log = structlog.get_logger()


# --- Pydantic Models for Configuration Structure ---


class CameraSettings(BaseModel):
    """Settings related to the camera source."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    index: int = Field(
        ...,
        ge=0,
        le=10,
        description="The index of the camera device (e.g., 0, 1). Valid range: 0-10.",
    )
    desired_width: int = Field(
        ...,
        gt=0,
        le=7680,
        description=(
            "The width (pixels) used for defining detection zones. Valid range: 1-7680 (8K max)."
        ),
    )
    desired_height: int = Field(
        ...,
        gt=0,
        le=4320,
        description=(
            "The height (pixels) used for defining detection zones. Valid range: 1-4320 (8K max)."
        ),
    )
    max_reconnect_attempts: int = Field(
        10,
        ge=0,
        description="Maximum reconnection attempts before giving up (0 = infinite)",
    )
    reconnect_timeout_seconds: float = Field(
        60.0,
        ge=0.0,
        description="Total time to keep trying to reconnect (0 = no timeout)",
    )
    max_frame_lag_ms: float = Field(
        500.0,
        ge=0.0,
        description="Warn if frame lag exceeds this threshold (ms)",
    )


class LiveAnalysisSettings(BaseModel):
    """Settings for live camera analysis sessions."""

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    default_duration_s: float = Field(
        300.0,
        gt=0.0,
        le=7200.0,
        description="Default duration for live analysis sessions (seconds, max 2 hours)",
    )
    max_duration_s: float = Field(
        7200.0,
        gt=0.0,
        description="Maximum allowed duration for live analysis sessions (seconds)",
    )
    auto_stop_on_limit: bool = Field(
        True,
        description="Automatically stop recording when duration limit is reached",
    )
    show_countdown: bool = Field(
        True,
        description="Show countdown timer before starting live analysis",
    )
    countdown_duration_s: int = Field(
        5,
        ge=0,
        le=60,
        description="Countdown duration in seconds before starting analysis",
    )


class ArduinoSettings(BaseModel):
    """Settings for connecting to an Arduino device."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    port: str = Field(
        ...,
        min_length=1,
        description=(
            "The serial port the Arduino is connected to (e.g., 'COM5' or '/dev/ttyACM0')."
        ),
    )
    baud_rate: int = Field(
        ...,
        ge=300,
        le=2000000,
        description="The baud rate for serial communication. Valid range: 300-2000000.",
    )


class RecorderSettings(BaseModel):
    """Settings for Parquet/video recorder behavior."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

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

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    path: str = Field(
        ...,
        min_length=1,
        description="Path to the YOLO model weights file (e.g., 'model.pt').",
    )

    @field_validator("path")
    @classmethod
    def validate_model_path_exists(cls, v: str) -> str:
        """Validate that model file exists and is readable.

        Note: If model file doesn't exist, logs warning but allows configuration
        to load (useful for development/testing). Application will fail at
        detection time if model is truly missing.
        """
        # 1. Check absolute path or relative to CWD
        path_cwd = Path(v)
        if path_cwd.exists() and path_cwd.is_file():
            return str(path_cwd.resolve())

        # 2. Check relative to project root (assuming src layout)
        # Location: src/zebtrack/settings.py
        # .parent -> src/zebtrack
        # .parent.parent -> src
        # .parent.parent.parent -> Project Root
        project_root = Path(__file__).parent.parent.parent
        path_project = project_root / v

        if path_project.exists() and path_project.is_file():
            return str(path_project.resolve())

        # 3. Fallback / Not Found logic
        # Use the CWD path for the warning message as it's the most intuitive context
        log.warning(
            "yolo_model.path.not_found",
            path=v,
            resolved_path=str(path_project),
            message="Model file not found. Detection will fail until model is available.",
        )
        return v

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
        description=("Non-Maximum Suppression threshold for filtering overlapping bounding boxes."),
    )

    # OPTIMIZATION: Inference performance settings
    use_half_precision: bool = Field(
        True,
        description=(
            "Enable FP16 (half precision) inference for faster GPU processing. "
            "Automatically disabled if CUDA is not available. "
            "Provides ~2x speedup with minimal accuracy impact on modern NVIDIA GPUs."
        ),
    )
    inference_size: int = Field(
        640,
        ge=320,
        le=1280,
        description=(
            "Input image size for YOLO inference. Smaller values (416, 512) are faster "
            "but may reduce accuracy for small objects. Valid range: 320-1280. "
            "Must be divisible by 32. Default 640 balances speed and accuracy."
        ),
    )

    @field_validator("inference_size")
    @classmethod
    def validate_inference_size_divisible_by_32(cls, v: int) -> int:
        """Ensure inference size is divisible by 32 (YOLO requirement)."""
        if v % 32 != 0:
            raise ValueError(
                f"inference_size must be divisible by 32, got {v}. "
                f"Try: {(v // 32) * 32} or {((v // 32) + 1) * 32}"
            )
        return v


class ByteTrackSettings(BaseModel):
    """Association thresholds for the ByteTrack tracker.

    Enhanced with hybrid matching support for sparse frame processing scenarios
    (e.g., analyzing every N frames) where small, fast-moving objects can move
    significantly between processed frames.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    track_threshold: float = Field(
        0.1,
        gt=0,
        lt=1,
        description=(
            "Minimum score required to keep a detection associated with an existing "
            "track during the ByteTrack matching stage."
        ),
    )
    match_threshold: float = Field(
        0.95,
        gt=0,
        le=1,
        description=(
            "Threshold used when linking unmatched detections to existing tracks in "
            "ByteTrack's second association pass. Higher values (0.7-0.95) improve ID "
            "stability. Value represents max acceptable cost (0=perfect match, 1=worst)."
        ),
    )
    max_center_distance: float = Field(
        200.0,
        gt=0,
        description=(
            "Maximum center-to-center distance (in pixels) for hybrid matching fallback. "
            "When IoU-based matching fails (no bbox overlap), ByteTrack falls back to "
            "center distance matching. This is useful for small, fast-moving objects "
            "like zebrafish that can move significantly between frames. "
            "Default 1000px allows matching movements across almost the entire aquarium."
        ),
    )
    track_buffer: int = Field(
        300,
        ge=10,
        le=1000,
        description=(
            "Number of frames to keep a lost track before removing it. Higher values "
            "allow re-identification after longer occlusions. Scaled by processing_interval "
            "internally. Default 90 with interval=5 means track survives ~18 detection cycles."
        ),
    )
    iou_threshold: float = Field(
        0.1,
        ge=0,
        lt=1,
        description=(
            "Minimum IoU overlap to prefer IoU-based matching over center distance. "
            "Lower values (0.0-0.1) make the tracker rely more on center distance, "
            "which is better for small, fast-moving objects with little overlap between frames."
        ),
    )


class VideoProcessingSettings(BaseModel):
    """Settings for processing video files or live streams."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    fps: int = Field(
        ...,
        gt=0,
        le=120,
        description="Frames Per Second (FPS) for saving output videos. Valid range: 1-120.",
    )
    pixel_cm: float | None = Field(
        None,
        ge=0.0,
        description="Global default pixels-per-cm calibration value (optional).",
    )
    processing_interval: int = Field(
        ...,
        ge=1,
        le=1000,
        description="Process 1 frame every N frames to optimize performance. Valid range: 1-1000.",
    )
    display_interval: int = Field(
        5,
        ge=1,
        le=1000,
        description="Update UI preview every N frames. Valid range: 1-1000.",
    )
    processing_offset: int = Field(
        ...,
        ge=0,
        description=(
            "Frame offset for processing. E.g., offset=1 and interval=10 processes "
            "frames 1, 11, 21, ... Must be non-negative."
        ),
    )
    calculate_angles: bool = Field(
        True,
        description="Whether to calculate angular velocity metrics.",
    )
    sharp_turn_threshold_deg_s: float = 200.0
    freezing_velocity_threshold: float = 1.5
    freezing_min_duration_s: float = 1.0
    # Single animal tracking mode
    single_animal_per_aquarium: bool = Field(
        False,
        description="When True, forces consistent track_id=1 for single animal scenarios.",
    )
    batch_retry_strategy: Literal["continue", "stop"] = Field(
        "continue",
        description="Behavior when a video fails in batch processing: 'continue' or 'stop'.",
    )


class TrajectorySmoothingSettings(BaseModel):
    """Smoothing parameters applied to trajectory preprocessing."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    enabled: bool = Field(
        True,
        description="Enable trajectory smoothing using Savitzky-Golay filter.",
    )
    window_length: int = Field(
        7,
        ge=3,
        description=(
            "Odd-sized window used by the Savitzky-Golay filter during trajectory smoothing."
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
            raise ValueError("trajectory_smoothing.window_length must be an odd integer.")
        return value

    @model_validator(mode="after")
    def _validate_polyorder(self) -> "TrajectorySmoothingSettings":
        if self.polyorder >= self.window_length:
            raise ValueError("trajectory_smoothing.polyorder must be less than window_length.")
        return self


class AngularVelocitySettings(BaseModel):
    """Parameters for robust angular velocity calculation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

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
                "angular_velocity.angular_velocity_smoothing_window must be odd or equal to 1."
            )
        return value


class TrackingSettings(BaseModel):
    """Toggle options that affect tracker selection and behavior."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    use_bytetrack: bool = Field(
        True,
        description=(
            "When True, use the advanced ByteTrack algorithm (Kalman Filter + IoU). "
            "When False, falls back to a simpler hybrid tracker (IoU + Distance) "
            "optimized for single-subject scenarios. Disable only if ByteTrack fails "
            "or for diagnostic purposes."
        ),
    )

    use_single_subject_tracker: bool = Field(
        False,
        description=(
            "Legacy flag: When True, prefer the lightweight single-subject tracker. "
            "Now largely superseded by 'use_bytetrack=False'."
        ),
    )


class DetectionZonesSettings(BaseModel):
    """Defines the coordinates for areas of interest in the camera frame."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    polygon: list[list[int]] = Field(
        default_factory=list,
        description="A list of [x, y] points defining the main detection polygon.",
    )
    roi_polygons: list[list[list[int]]] = Field(
        default_factory=list,
        description="A list of polygons, where each polygon is a list of [x,y] points.",
    )
    roi_names: list[str] = Field(
        default_factory=list,
        description="The names for each ROI polygon.",
    )
    roi_colors: list[tuple[int, int, int]] = Field(
        default_factory=list,
        description="The BGR colors for drawing each ROI polygon on the overlay.",
    )

    # Aquarium detection constraints
    min_aquarium_area_ratio: float = Field(
        0.10,
        ge=0.01,
        le=0.9,
        description=(
            "Minimum area ratio (relative to frame size) for a detection to be considered "
            "a valid aquarium. Default 0.10 (10%)."
        ),
    )
    max_aquarium_area_ratio: float = Field(
        0.98,
        ge=0.1,
        le=1.0,
        description=(
            "Maximum area ratio (relative to frame size) for a detection to be considered "
            "a valid aquarium. Default 0.98 (98%) to avoid full-frame false positives."
        ),
    )


class ReproducibilitySettings(BaseModel):
    """Settings related to ensuring reproducible results."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    seed: int = Field(
        42,
        description=(
            "Seed for random number generators (numpy, torch) to ensure consistent results."
        ),
    )


class OpenVINOSettings(BaseModel):
    """OpenVINO-specific configuration settings.

    These settings control how OpenVINO is used for model inference.
    The system can auto-detect optimal settings via hardware benchmark,
    or you can override them manually here.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    device: Literal["AUTO", "CPU", "GPU"] = Field(
        "AUTO",
        description=(
            "OpenVINO device for inference. 'AUTO' lets OpenVINO choose, "
            "'CPU' forces CPU, 'GPU' forces Intel GPU. "
            "Use 'AUTO' unless benchmark shows specific device is faster."
        ),
    )
    device_batch: Literal["AUTO", "CPU", "GPU"] = Field(
        "AUTO",
        description=(
            "OpenVINO device for batch/offline video processing. "
            "Can be different from live camera device."
        ),
    )
    performance_hint_live: Literal["LATENCY", "THROUGHPUT"] = Field(
        "LATENCY",
        description=(
            "Performance hint for live camera analysis. "
            "'LATENCY' minimizes per-frame delay (recommended for real-time). "
            "'THROUGHPUT' maximizes frames/second (may increase latency)."
        ),
    )
    performance_hint_batch: Literal["LATENCY", "THROUGHPUT"] = Field(
        "LATENCY",
        description=(
            "Performance hint for batch video processing. "
            "Note: 'THROUGHPUT' may be slower on Intel integrated GPUs (Iris Xe). "
            "Benchmark will auto-detect the best setting."
        ),
    )
    precision: Literal["FP32", "FP16", "INT8"] = Field(
        "FP32",
        description=(
            "Inference precision. 'FP32' is default, 'FP16' can be faster on some GPUs, "
            "'INT8' requires quantized model but can be 2x faster."
        ),
    )
    enable_model_cache: bool = Field(
        True,
        description=(
            "Cache compiled models to speed up startup. "
            "First run compiles kernels (30-60s), subsequent runs load from cache."
        ),
    )
    cache_dir: str = Field(
        "openvino_model_cache/compiled_cache",
        description="Directory for cached compiled models.",
    )
    auto_benchmark: bool = Field(
        True,
        description=(
            "Automatically run hardware benchmark on first startup to detect "
            "optimal settings. Results are cached and reused."
        ),
    )
    batch_nireq: int = Field(
        4,
        ge=1,
        le=16,
        description=(
            "Number of parallel inference requests for batch mode "
            "(AsyncInferQueue pool size). Higher values overlap more "
            "preprocessing with inference but consume more memory. "
            "Typical range: 2-8. Default 4 balances throughput vs memory."
        ),
    )


class ModelSelectionSettings(BaseModel):
    """Settings for selecting which model type to use for different tasks."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    aquarium_method: Literal["seg", "det"] = Field(
        "seg",
        description=("Method for aquarium detection: 'seg' for segmentation, 'det' for detection"),
    )
    animal_method: Literal["seg", "det"] = Field(
        "det",
        description=("Method for animal tracking: 'seg' for segmentation, 'det' for detection"),
    )
    use_openvino: bool = Field(
        False,
        description="Whether to use OpenVINO for model inference (auto-detected if not set)",
    )


class WeightsSelectionSettings(BaseModel):
    """Settings for weight file selection by type."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

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

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    use_wizard_for_project_creation: bool = Field(
        True,
        description="Use new 5-step wizard instead of legacy CreateProjectDialog (v1.6+ default)",
    )
    enable_event_queue: bool = Field(
        False,
        description=(
            "Route controller→GUI interactions through the async event queue "
            "instead of direct Tkinter calls. Staged migration feature (Phase 1). "
            "Default: False for stability."
        ),
    )
    suppress_roi_mismatch_warning: bool = Field(
        False,
        description=(
            "Suppress warning dialog when generating unified reports with videos that have "
            "different ROI configurations. Enable this if you understand the implications "
            "of merging data from videos with different ROI schemas."
        ),
    )


class PerformanceSettings(BaseModel):
    """Performance and parallelization settings (Phase 8)."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    max_parallel_videos: int = Field(
        2,
        ge=1,
        le=4,
        description=(
            "Maximum number of videos to process in parallel. "
            "Higher values increase throughput but consume more RAM. "
            "Recommended: 2-3 for typical systems."
        ),
    )
    max_parallel_plots: int = Field(
        3,
        ge=1,
        le=5,
        description=(
            "Maximum number of matplotlib plots to generate in parallel during report generation. "
            "Higher values speed up report generation but may cause thread contention. "
            "Recommended: 3 for optimal performance."
        ),
    )
    parquet_compression: Literal["snappy", "gzip", "none"] = Field(
        "snappy",
        description=(
            "Compression codec for Parquet files. "
            "'snappy': Fast compression with good ratio (default). "
            "'gzip': Better compression ratio but slower. "
            "'none': No compression, fastest but larger files."
        ),
    )
    enable_parallel_analysis: bool = Field(
        True,
        description=(
            "Enable parallel execution of independent analysis components. "
            "When True, BehavioralAnalyzer and ROIAnalyzer may run concurrently where possible."
        ),
    )


class LoggingSettings(BaseModel):
    """Settings for per-module logging levels."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    levels: dict[str, str] = Field(
        default_factory=lambda: {
            "zebtrack": "INFO",
            "zebtrack.core.detection": "INFO",
            "zebtrack.ui": "WARNING",
            "zebtrack.io": "WARNING",
            "zebtrack.analysis": "INFO",
        },
        description="Per-module log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, v):
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        for module, level in v.items():
            if level.upper() not in valid_levels:
                raise ValueError(f"Invalid log level '{level}' for module '{module}'")
        # Return uppercase values to be stored in the model
        return {k: v.upper() for k, v in v.items()}


class BehavioralAnalysisSettings(BaseModel):
    """Default settings for behavioral analysis metrics.

    These settings control the default values for thigmotaxis and geotaxis calculations.
    Users can override these values in the wizard or analysis dialogs.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    default_thigmotaxis_distance_cm: float = Field(
        1.5,
        ge=0.1,
        le=10.0,
        description="Default distance threshold (cm) for thigmotaxis 'near wall' calculation",
    )
    default_geotaxis_distance_cm: float = Field(
        1.5,
        ge=0.1,
        le=10.0,
        description="Default distance threshold (cm) for geotaxis 'near bottom' calculation",
    )
    default_geotaxis_num_zones: int = Field(
        3,
        ge=2,
        le=10,
        description="Default number of vertical zones for geotaxis zone mode",
    )
    default_geotaxis_bottom_zones: int = Field(
        1,
        ge=1,
        le=2,
        description="Default number of bottom zones to consider as 'bottom' (1 or 2)",
    )
    aquarium_perspective: Literal["top_down", "lateral"] = Field(
        "lateral",
        description="Default perspective of the aquarium ('top_down' or 'lateral').",
    )
    geotaxis_mode: Literal["distance", "zones"] = Field(
        "zones",
        description="Default method for geotaxis calculation ('distance' or 'zones').",
    )


class AnalysisConfigSettings(BaseModel):
    """Configuration for analysis parameters."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    num_aquariums: int = Field(
        1,
        ge=1,
        le=4,
        description="Number of aquariums expected in the video (1 or 2 currently supported).",
    )


class Settings(BaseModel):
    """Main settings model that nests all other configuration sections.

    This model enforces strict validation rules and prevents unknown fields
    to catch configuration errors early. All nested models use sensible defaults
    where appropriate.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    # Required core settings (no defaults)
    camera: CameraSettings
    arduino: ArduinoSettings
    yolo_model: YOLOModelSettings
    video_processing: VideoProcessingSettings
    reproducibility: ReproducibilitySettings

    # Optional settings with defaults
    recorder: RecorderSettings = Field(
        default_factory=RecorderSettings,
        description="Settings for Parquet/video recorder behavior",
    )
    live_analysis: LiveAnalysisSettings = Field(
        default_factory=LiveAnalysisSettings,
        description="Settings for live camera analysis sessions",
    )
    bytetrack: ByteTrackSettings = Field(
        default_factory=ByteTrackSettings,
        description="Default thresholds used by the ByteTrack tracker.",
    )
    tracking: TrackingSettings = Field(
        default_factory=TrackingSettings,
        description="Tracker selection toggles and preferences.",
    )
    detection_zones: DetectionZonesSettings = Field(
        default_factory=DetectionZonesSettings,
        description="Coordinates for areas of interest in the camera frame.",
    )

    # Model selection and weights
    model_selection: ModelSelectionSettings = Field(
        default_factory=ModelSelectionSettings,
        description="Settings for selecting model types (seg/det) for different tasks",
    )
    weights: WeightsSelectionSettings = Field(
        default_factory=WeightsSelectionSettings,
        description="Settings for weight file selection by type",
    )
    openvino: OpenVINOSettings = Field(
        default_factory=OpenVINOSettings,
        description="OpenVINO-specific settings for GPU inference optimization",
    )

    # ROI inclusion rule settings
    roi_inclusion_rule: Literal[
        "centroid_in",
        "centroid_in_on_buffered_roi",
        "bbox_intersects",
        "seg_overlap",
    ] = Field(
        default="bbox_intersects",
        description="Algorithm used to determine if an animal is inside an ROI",
    )
    roi_buffer_radius_value: float = Field(
        default=0.5,
        ge=0.0,
        description="Buffer radius for centroid_in_on_buffered_roi mode (in pixels or cm)",
    )
    roi_min_bbox_overlap_ratio: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Minimum overlap ratio required for bbox_intersects or seg_overlap",
    )

    analysis_config: "AnalysisConfigSettings" = Field(
        default_factory=AnalysisConfigSettings,
        description="Configuration for analysis parameters like number of aquariums.",
    )
    behavioral_analysis: BehavioralAnalysisSettings = Field(
        default_factory=BehavioralAnalysisSettings,
        description="Default settings for thigmotaxis and geotaxis behavioral metrics.",
    )

    # Analysis settings
    ui_features: UIFeatureFlags = Field(
        default_factory=UIFeatureFlags,
        description="Feature flags for UI experiments and gradual rollouts",
    )
    trajectory_smoothing: TrajectorySmoothingSettings = Field(
        default_factory=TrajectorySmoothingSettings,
        description="Smoothing parameters applied to trajectory preprocessing.",
    )
    angular_velocity: AngularVelocitySettings = Field(
        default_factory=AngularVelocitySettings,
        description=(
            "Parameters for robust angular velocity calculation to handle detection jitter."
        ),
    )
    performance: PerformanceSettings = Field(
        default_factory=PerformanceSettings,
        description=(
            "Performance and parallelization settings for optimizing throughput (Phase 8)."
        ),
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Per-module logging level configuration.",
    )

    @model_validator(mode="after")
    def _validate_advanced_constraints(self) -> "Settings":
        """Ensure cross-field invariants that depend on multiple settings."""

        # Validate processing interval/offset relationship
        interval = self.video_processing.processing_interval
        offset = self.video_processing.processing_offset
        if interval <= 0:
            raise ValueError("video_processing.processing_interval must be a positive integer.")
        if offset < 0:
            raise ValueError(
                "video_processing.processing_offset must be greater than or equal to 0."
            )
        if offset >= interval:
            raise ValueError(
                "video_processing.processing_offset must be less than processing_interval."
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


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries, with override taking precedence.

    This function performs a deep merge where:
    - Nested dictionaries are recursively merged
    - Lists and other values from override completely replace base values
    - Keys only in base are preserved
    - Keys only in override are added

    Args:
        base: The base dictionary (lower priority)
        override: The override dictionary (higher priority)

    Returns:
        A new merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(
    default_config_path: Path | str = Path("config.yaml"),
    override_config_path: Path | str = Path("config.local.yaml"),
) -> Settings:
    """Load and validate application settings from YAML configuration files.

    This function implements a hierarchical configuration system:
    1. Loads the base configuration from `default_config_path`
    2. If `override_config_path` exists, recursively merges its values on top
       of the base configuration (allowing local customization without modifying
       the main config file)
    3. Validates the merged configuration using Pydantic models
    4. Returns a fully validated Settings object with type-safe access

    The override file (config.local.yaml by default) should be git-ignored to
    allow developers to maintain machine-specific settings like camera indices,
    serial ports, or confidence thresholds without affecting the repository.

    Args:
        default_config_path: Path to the base configuration file (config.yaml)
        override_config_path: Path to the local override file (config.local.yaml)

    Returns:
        A validated Settings object with all configuration values

    Raises:
        FileNotFoundError: If the default config file does not exist
        ValueError: If YAML parsing fails or configuration validation fails

    Example:
        >>> settings = load_settings()
        >>> print(settings.camera.index)
        1
        >>> print(settings.yolo_model.confidence_threshold)
        0.05
    """
    default_config_path = (
        Path(default_config_path) if isinstance(default_config_path, str) else default_config_path
    )
    override_config_path = (
        Path(override_config_path)
        if isinstance(override_config_path, str)
        else override_config_path
    )
    if not default_config_path.is_file():
        log.error("settings.load.file_not_found", path=str(default_config_path))
        raise FileNotFoundError(f"Default configuration file not found at: {default_config_path}")

    log.info("settings.load.start", path=str(default_config_path))

    try:
        # Load base configuration
        with open(default_config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        # Merge with override configuration if it exists
        if override_config_path.is_file():
            log.info("settings.load.override", path=str(override_config_path))
            with open(override_config_path, encoding="utf-8") as f:
                override_data = yaml.safe_load(f)
            if override_data:
                config_data = _deep_merge_dicts(config_data, override_data)
                log.debug(
                    "settings.load.merged",
                    base_path=str(default_config_path),
                    override_path=str(override_config_path),
                )

        # Validate using Pydantic
        settings_obj = Settings.model_validate(config_data)
        log.info("settings.load.success", config_keys=list(config_data.keys()))
        return settings_obj

    except yaml.YAMLError as e:
        log.error("settings.load.yaml_error", error=str(e), path=str(default_config_path))
        raise ValueError(
            f"Failed to parse YAML configuration file '{default_config_path}': {e}"
        ) from e
    except ValidationError as e:
        log.error(
            "settings.load.validation_error",
            error=str(e),
            error_count=e.error_count(),
        )
        # Provide more detailed error information
        error_details = []
        for error in e.errors():
            field_path = " → ".join(str(loc) for loc in error["loc"])
            error_details.append(f"  • {field_path}: {error['msg']}")

        error_msg = (
            f"Configuration validation failed with {e.error_count()} error(s):\n"
            + "\n".join(error_details)
        )
        raise ValueError(error_msg) from e


def reload_settings(
    default_config_path: Path | str = Path("config.yaml"),
    override_config_path: Path | str = Path("config.local.yaml"),
) -> Settings:
    """Reload settings from disk, useful after editing configuration files.

    This is a convenience wrapper around load_settings() that explicitly
    communicates the intent to reload configuration at runtime (e.g., after
    the user has edited config.local.yaml through the GUI).

    Args:
        default_config_path: Path to the base configuration file
        override_config_path: Path to the local override file

    Returns:
        A freshly loaded and validated Settings object

    Example:
        >>> # User edits config via GUI
        >>> new_settings = reload_settings()
        >>> # Application now uses updated configuration
    """
    default_config_path = (
        Path(default_config_path) if isinstance(default_config_path, str) else default_config_path
    )
    override_config_path = (
        Path(override_config_path)
        if isinstance(override_config_path, str)
        else override_config_path
    )
    log.info("settings.reload.requested")
    return load_settings(default_config_path, override_config_path)


def save_settings(
    settings: Settings,
    target_path: Path | str = Path("config.local.yaml"),
) -> None:
    """Save the current settings to a YAML file.

    This allows persisting runtime configuration changes (like detector calibration)
    to disk so they survive application restarts. By default, saves to
    'config.local.yaml' to avoid modifying the version-controlled 'config.yaml'.

    Args:
        settings: The Settings object to save
        target_path: Path to the output YAML file (default: config.local.yaml)
    """
    target_path = Path(target_path) if isinstance(target_path, str) else target_path

    # Dump model to dict using json mode for better serialization compatibility
    config_data = settings.model_dump(mode="json")

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        log.info("settings.save.success", path=str(target_path))
    except Exception as e:
        log.error("settings.save.failed", path=str(target_path), error=str(e))
        raise


def export_schema(
    output_path: Path | None = None,
    indent: int = 2,
) -> dict[str, Any]:
    """Export the Settings JSON schema for documentation or validation purposes.

    This generates a complete JSON Schema document describing all configuration
    fields, their types, constraints, and descriptions. Useful for:
    - Generating configuration documentation
    - IDE autocomplete in YAML editors (via schema association)
    - External validation tools
    - API documentation generation

    Args:
        output_path: If provided, write the schema to this file as JSON
        indent: Number of spaces for JSON indentation (default: 2)

    Returns:
        The JSON Schema as a dictionary

    Example:
        >>> schema = export_schema(Path("config.schema.json"))
        >>> print(schema["properties"]["camera"]["properties"]["index"]["description"])
        The index of the camera device (e.g., 0, 1).
    """
    schema = Settings.model_json_schema()

    if output_path:
        import json

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=indent)
        log.info("settings.schema.exported", path=str(output_path))

    return schema


# =============================================================================
# Dependency Injection Pattern
# =============================================================================
#
# This module no longer exports a global `settings` singleton. Instead, all
# components receive settings via constructor injection through the Composition
# Root in __main__.py.
#
# Migration completed:
# ✅ Phase 1: Core services (WeightManager, DetectorService, ProjectManager, etc.)
# ✅ Phase 2: Analysis & IO layers (AnalysisService, Camera, Recorder, Plugins)
# ✅ Phase 3: UI layer (ApplicationGUI, WizardDialog, dialogs)
#
# All settings are now injected via the Composition Root pattern.


# =============================================================================
# Public API
# =============================================================================
__all__ = sorted(
    [
        # Settings model classes (for type hints and validation)
        "Settings",
        "CameraSettings",
        "ArduinoSettings",
        "RecorderSettings",
        "YOLOModelSettings",
        "ByteTrackSettings",
        "VideoProcessingSettings",
        "TrajectorySmoothingSettings",
        "AngularVelocitySettings",
        "TrackingSettings",
        "DetectionZonesSettings",
        "ReproducibilitySettings",
        "ModelSelectionSettings",
        "WeightsSelectionSettings",
        "UIFeatureFlags",
        "PerformanceSettings",
        "LoggingSettings",
        # Utility functions
        "load_settings",
        "reload_settings",
        "save_settings",
        "export_schema",
    ],
    key=str.casefold,
)
