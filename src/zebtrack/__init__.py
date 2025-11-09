"""ZebTrack-AI: Zebrafish behavioral tracking and analysis system."""

# Import and export custom exceptions for easy access
from zebtrack.exceptions import (
    AnalysisError,
    ArduinoConnectionError,
    ArduinoError,
    CameraConnectionError,
    CameraError,
    ConfigurationError,
    DetectorError,
    FileOperationError,
    FrameProcessingError,
    HardwareError,
    ModelError,
    ModelLoadError,
    ParquetError,
    ProcessingError,
    ProjectError,
    RecorderError,
    SettingsError,
    TrackingError,
    UIError,
    ValidationError,
    VideoSourceError,
    VideoWriteError,
    WizardError,
    ZebTrackError,
    ZoneError,
)

__version__ = "2.1.0"

__all__ = [
    "AnalysisError",
    "ArduinoConnectionError",
    "ArduinoError",
    "CameraConnectionError",
    "CameraError",
    # Configuration
    "ConfigurationError",
    # Detection and Tracking
    "DetectorError",
    # I/O and File Operations
    "FileOperationError",
    "FrameProcessingError",
    # Hardware
    "HardwareError",
    "ModelError",
    "ModelLoadError",
    "ParquetError",
    # Processing and Analysis
    "ProcessingError",
    "ProjectError",
    "RecorderError",
    "SettingsError",
    "TrackingError",
    # UI and User Input
    "UIError",
    "ValidationError",
    "VideoSourceError",
    "VideoWriteError",
    "WizardError",
    # Base exception
    "ZebTrackError",
    "ZoneError",
    # Version
    "__version__",
]
