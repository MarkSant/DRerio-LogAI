"""
Custom exception hierarchy for ZebTrack-AI.

All application exceptions inherit from ZebTrackError for easy catching.
"""

from __future__ import annotations

from pathlib import Path

# ============================================================================
# Base Exception
# ============================================================================


class ZebTrackError(Exception):
    """Base exception for all ZebTrack errors."""

    def __init__(self, *args: object, details: dict | None = None) -> None:
        """
        Initialize ZebTrackError with message and optional details.

        Args:
            *args: Positional arguments for Exception (typically error message)
            details: Optional dictionary with error context
        """
        super().__init__(*args)
        self.details = details or {}


# ============================================================================
# I/O and File Operations
# ============================================================================


class FileOperationError(ZebTrackError):
    """Base for file operation errors."""

    pass


class VideoNotFoundError(FileOperationError):
    """Video file not found."""

    pass


class VideoReadError(FileOperationError):
    """Error reading video file."""

    pass


class VideoSourceError(FileOperationError):
    """Error opening or reading video source."""

    pass


class VideoWriteError(FileOperationError):
    """Error writing video output."""

    pass


class CameraError(FileOperationError):
    """Error accessing camera hardware."""

    pass


class CameraNotFoundError(CameraError):
    """Camera device not found or not available."""

    pass


class CameraAccessError(CameraError):
    """Permission denied accessing camera."""

    pass


class CameraConnectionError(CameraError):
    """Failed to connect to camera."""

    pass


class RecorderError(FileOperationError):
    """Error in recording system."""

    pass


class ParquetError(FileOperationError):
    """Error reading/writing Parquet files."""

    pass


# ============================================================================
# Detection and Tracking
# ============================================================================


class DetectorError(ZebTrackError):
    """Base for detector errors."""

    pass


class ModelLoadError(DetectorError):
    """Failed to load detection model."""

    pass


class ModelError(DetectorError):
    """Error during model inference."""

    pass


class TrackingError(ZebTrackError):
    """Error in tracking system."""

    pass


class ZoneError(ZebTrackError):
    """Error in zone configuration or scaling."""

    pass


# ============================================================================
# Processing and Analysis
# ============================================================================


class ProcessingError(ZebTrackError):
    """Base for processing errors."""

    pass


class FrameProcessingError(ProcessingError):
    """Error processing a video frame."""

    pass


class AnalysisError(ZebTrackError):
    """Error during behavioral analysis."""

    pass


# ============================================================================
# Hardware
# ============================================================================


class HardwareError(ZebTrackError):
    """Base for hardware errors."""

    pass


class ArduinoError(HardwareError):
    """Error communicating with Arduino."""

    pass


class ArduinoConnectionError(ArduinoError):
    """Failed to connect to Arduino."""

    pass


# ============================================================================
# UI and User Input
# ============================================================================


class UIError(ZebTrackError):
    """Base for UI errors."""

    pass


class ValidationError(UIError):
    """User input validation failed."""

    pass


class WizardError(UIError):
    """Error in wizard workflow."""

    pass


# ============================================================================
# Configuration
# ============================================================================


class ConfigurationError(ZebTrackError):
    """Base for configuration errors."""

    pass


class SettingsError(ConfigurationError):
    """Error in settings validation or loading."""

    pass


class ProjectError(ConfigurationError):
    """Error in project configuration."""

    pass


class ProjectNotFoundError(ProjectError):
    """Project file not found."""

    pass


class ProjectLoadError(ProjectError):
    """Error loading project file."""

    pass


class ProjectSaveError(ProjectError):
    """Error saving project file."""

    pass


class ProjectInvalidError(ProjectError):
    """Exception raised when project structure or data is invalid.

    Raised when:
    - Project directory cannot be created
    - Project configuration file is missing or not found
    - Project configuration is corrupted or contains invalid JSON
    - Project file save operation fails due to permissions or disk errors

    This exception replaces GUI messagebox calls for thread-safe error handling
    and allows calling code to handle project validation errors appropriately.

    Attributes:
        path: Optional Path to the project directory or file involved
        cause: Optional underlying exception that caused this error
    """

    def __init__(
        self,
        message: str,
        path: Path | str | None = None,
        cause: Exception | None = None,
        *,
        details: dict | None = None,
    ):
        """Initialize ProjectInvalidError with structured error information.

        Args:
            message: Human-readable error description
            path: Optional path to the project directory or file involved
            cause: Optional underlying exception that caused this error
            details: Optional dictionary with error context
        """
        from pathlib import Path

        self.path = Path(path) if path and not isinstance(path, Path) else path
        self.cause = cause
        super().__init__(message, details=details)


# ============================================================================
# Export for convenience
# ============================================================================

__all__ = [  # noqa: RUF022 - grouped by domain for clarity
    "ZebTrackError",
    # I/O
    "FileOperationError",
    "VideoNotFoundError",
    "VideoReadError",
    "VideoSourceError",
    "VideoWriteError",
    "CameraError",
    "CameraNotFoundError",
    "CameraAccessError",
    "CameraConnectionError",
    "RecorderError",
    "ParquetError",
    # Detection
    "DetectorError",
    "ModelLoadError",
    "ModelError",
    "TrackingError",
    "ZoneError",
    # Processing
    "ProcessingError",
    "FrameProcessingError",
    "AnalysisError",
    # Hardware
    "HardwareError",
    "ArduinoError",
    "ArduinoConnectionError",
    # UI
    "UIError",
    "ValidationError",
    "WizardError",
    # Configuration
    "ConfigurationError",
    "SettingsError",
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectLoadError",
    "ProjectSaveError",
    "ProjectInvalidError",
]
