"""
This module defines the Pydantic models for application settings and provides
a loader function to read and validate the configuration from a YAML file.
"""

import logging
from pathlib import Path
from typing import List, Tuple

import yaml
from pydantic import BaseModel, Field, ValidationError

# --- Pydantic Models for Configuration Structure ---


class CameraSettings(BaseModel):
    index: int
    desired_width: int
    desired_height: int


class ArduinoSettings(BaseModel):
    port: str
    baud_rate: int


class YOLOModelSettings(BaseModel):
    path: str
    confidence_threshold: float = Field(..., gt=0, lt=1)
    nms_threshold: float = Field(..., gt=0, lt=1)


class VideoProcessingSettings(BaseModel):
    fps: int
    processing_interval: int
    processing_offset: int


class DetectionZonesSettings(BaseModel):
    polygon: List[List[int]]
    squares: List[Tuple[Tuple[int, int], Tuple[int, int]]]
    colors: List[Tuple[int, int, int]]
    enter_commands: List[int]
    exit_commands: List[int]


class Settings(BaseModel):
    """Main settings model that nests all other configuration sections."""

    camera: CameraSettings
    arduino: ArduinoSettings
    yolo_model: YOLOModelSettings
    video_processing: VideoProcessingSettings
    detection_zones: DetectionZonesSettings


def load_settings(config_path: Path = Path("config.yaml")) -> Settings:
    """
    Loads, validates, and returns the application settings from a YAML file.

    Args:
        config_path (Path): The path to the configuration file.
                            Defaults to 'config.yaml' in the current directory.

    Returns:
        Settings: A validated Pydantic settings object.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config file has validation errors.
    """
    if not config_path.is_file():
        logging.error(f"Configuration file not found at: {config_path}")
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    logging.info(f"Loading settings from {config_path}...")
    try:
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)

        settings = Settings.model_validate(config_data)
        logging.info("Settings loaded and validated successfully.")
        return settings
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")
        raise ValueError(f"Error parsing YAML file: {e}")
    except ValidationError as e:
        logging.error(f"Configuration validation error: {e}")
        raise ValueError(f"Configuration validation error: {e}")


# Load settings once on module import to be used across the application
try:
    settings = load_settings()
except (FileNotFoundError, ValueError) as e:
    logging.critical(f"Failed to load application settings: {e}")
    # In a real app, you might want to exit or use default settings
    settings = None
