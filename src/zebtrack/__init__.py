"""ZebTrack-AI: Zebrafish behavioral tracking and analysis system."""

# Import and export custom exceptions for easy access
from zebtrack.core.exceptions import (
    AnalysisError,
    ArduinoConnectionError,
    ArduinoError,
    CameraAccessError,
    CameraConnectionError,
    CameraError,
    CameraNotFoundError,
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
    ProjectLoadError,
    ProjectNotFoundError,
    ProjectSaveError,
    RecorderError,
    SettingsError,
    TrackingError,
    UIError,
    ValidationError,
    VideoNotFoundError,
    VideoReadError,
    VideoSourceError,
    VideoWriteError,
    WizardError,
    ZebTrackError,
    ZoneError,
)

__version__ = "4.0.0"

__all__ = [
    "AnalysisError",
    "ArduinoConnectionError",
    "ArduinoError",
    "CameraAccessError",
    "CameraConnectionError",
    "CameraError",
    "CameraNotFoundError",
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
    "ProjectLoadError",
    "ProjectNotFoundError",
    "ProjectSaveError",
    "RecorderError",
    "SettingsError",
    "TrackingError",
    # UI and User Input
    "UIError",
    "ValidationError",
    "VideoNotFoundError",
    "VideoReadError",
    "VideoSourceError",
    "VideoWriteError",
    "WizardError",
    # Base exception
    "ZebTrackError",
    "ZoneError",
    # Version
    "__version__",
]
