"""
This module defines the Pydantic models for application settings and provides
a loader function to read and validate the configuration from a YAML file.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Union

import structlog
import yaml
from pydantic import BaseModel, Field, ValidationError

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


class DetectionZonesSettings(BaseModel):
    """Defines the coordinates for areas of interest in the camera frame."""

    polygon: List[List[int]] = Field(
        default_factory=list,
        description="A list of [x, y] points defining the main detection polygon.",
    )
    squares: List[Tuple[Tuple[int, int], Tuple[int, int]]] = Field(
        default_factory=list,
        description=(
            "A list of rectangular zones, each defined by top-left and "
            "bottom-right points."
        ),
    )
    colors: List[Tuple[int, int, int]] = Field(
        default_factory=list,
        description="The BGR colors for drawing each square on the overlay.",
    )
    enter_commands: List[Union[int, str]] = Field(
        default_factory=list,
        description=(
            "List of commands to send to Arduino when an object enters a square."
        ),
    )
    exit_commands: List[Union[int, str]] = Field(
        default_factory=list,
        description=(
            "List of commands to send to Arduino when an object exits a square."
        ),
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


class Settings(BaseModel):
    """Main settings model that nests all other configuration sections."""

    camera: CameraSettings
    arduino: ArduinoSettings
    yolo_model: YOLOModelSettings
    video_processing: VideoProcessingSettings
    detection_zones: DetectionZonesSettings = Field(default_factory=DetectionZonesSettings)
    reproducibility: ReproducibilitySettings


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
        with open(default_config_path, "r") as f:
            config_data = yaml.safe_load(f)

        if override_config_path.is_file():
            log.info("settings.load.override", path=str(override_config_path))
            with open(override_config_path, "r") as f:
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
