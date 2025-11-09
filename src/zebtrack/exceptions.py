"""
Custom exception hierarchy for ZebTrack-AI.

All application exceptions inherit from ZebTrackError for easy catching and
to distinguish application errors from system errors.

Exception Hierarchy:
    ZebTrackError (base)
    ├── FileOperationError
    │   ├── VideoSourceError
    │   ├── VideoWriteError
    │   ├── CameraError
    │   │   └── CameraConnectionError
    │   ├── RecorderError
    │   └── ParquetError
    ├── DetectorError
    │   ├── ModelLoadError
    │   └── ModelError
    ├── TrackingError
    ├── ZoneError
    ├── ProcessingError
    │   └── FrameProcessingError
    ├── AnalysisError
    ├── HardwareError
    │   └── ArduinoError
    │       └── ArduinoConnectionError
    ├── UIError
    │   ├── ValidationError
    │   └── WizardError
    └── ConfigurationError
        ├── SettingsError
        └── ProjectError
"""


# ============================================================================
# Base Exception
# ============================================================================


class ZebTrackError(Exception):
    """Base exception for all ZebTrack errors.

    All custom exceptions in ZebTrack inherit from this class, allowing
    consumers to catch all application errors with a single except clause.
    """

    pass


# ============================================================================
# I/O and File Operations
# ============================================================================


class FileOperationError(ZebTrackError):
    """Base exception for file I/O and data persistence errors.

    Raised when there are issues with reading, writing, or accessing files
    and data storage systems.
    """

    pass


class VideoSourceError(FileOperationError):
    """Error opening or reading from a video source.

    Raised when a video file cannot be opened, is corrupted, has an
    unsupported format, or encounters read errors during processing.
    """

    pass


class VideoWriteError(FileOperationError):
    """Error writing video output.

    Raised when there are issues creating or writing to video output files,
    including codec errors, disk space issues, or permission problems.
    """

    pass


class CameraError(FileOperationError):
    """Error accessing camera hardware.

    Base exception for camera-related errors, including connection issues,
    hardware failures, or configuration problems.
    """

    pass


class CameraConnectionError(CameraError):
    """Failed to connect to camera device.

    Raised when a camera device cannot be accessed, is not found, or fails
    to initialize properly.
    """

    pass


class RecorderError(FileOperationError):
    """Error in the recording system.

    Raised when there are issues with the video or data recording pipeline,
    including frame capture failures or storage errors.
    """

    pass


class ParquetError(FileOperationError):
    """Error reading or writing Parquet files.

    Raised when there are issues with Parquet data persistence, including
    schema validation errors, corrupted files, or incompatible versions.
    """

    pass


# ============================================================================
# Detection and Tracking
# ============================================================================


class DetectorError(ZebTrackError):
    """Base exception for detection system errors.

    Raised when there are issues with object detection, including model
    loading, inference, or configuration problems.
    """

    pass


class ModelLoadError(DetectorError):
    """Failed to load detection model.

    Raised when a detection model file cannot be found, is corrupted,
    has an incompatible format, or fails to initialize.
    """

    pass


class ModelError(DetectorError):
    """Error during model inference.

    Raised when there are runtime errors during model inference, including
    invalid input shapes, inference failures, or model execution errors.
    """

    pass


class TrackingError(ZebTrackError):
    """Error in the object tracking system.

    Raised when there are issues with tracking objects across frames,
    including track ID assignment, association failures, or state errors.
    """

    pass


class ZoneError(ZebTrackError):
    """Error in zone configuration or scaling.

    Raised when there are issues with zone definitions, coordinate
    transformations, or zone-related calculations.
    """

    pass


# ============================================================================
# Processing and Analysis
# ============================================================================


class ProcessingError(ZebTrackError):
    """Base exception for video processing errors.

    Raised when there are general issues during video processing workflows
    that don't fit into more specific error categories.
    """

    pass


class FrameProcessingError(ProcessingError):
    """Error processing a video frame.

    Raised when there are issues processing individual frames, including
    decoding errors, transformation failures, or analysis errors.
    """

    pass


class AnalysisError(ZebTrackError):
    """Error during behavioral analysis.

    Raised when there are issues during behavioral analysis computations,
    including metric calculation errors, invalid data, or analysis failures.
    """

    pass


# ============================================================================
# Hardware
# ============================================================================


class HardwareError(ZebTrackError):
    """Base exception for hardware integration errors.

    Raised when there are issues with external hardware devices,
    including communication failures or device errors.
    """

    pass


class ArduinoError(HardwareError):
    """Error communicating with Arduino device.

    Raised when there are issues with Arduino communication, including
    protocol errors, command failures, or state inconsistencies.
    """

    pass


class ArduinoConnectionError(ArduinoError):
    """Failed to connect to Arduino device.

    Raised when an Arduino device cannot be found, accessed, or fails
    to establish a connection.
    """

    pass


# ============================================================================
# UI and User Input
# ============================================================================


class UIError(ZebTrackError):
    """Base exception for user interface errors.

    Raised when there are issues with the UI layer, including rendering
    problems, event handling errors, or user interaction failures.
    """

    pass


class ValidationError(UIError):
    """User input validation failed.

    Raised when user-provided input fails validation checks, including
    invalid formats, out-of-range values, or constraint violations.
    """

    pass


class WizardError(UIError):
    """Error in wizard workflow.

    Raised when there are issues with the project setup wizard, including
    navigation errors, state inconsistencies, or workflow failures.
    """

    pass


# ============================================================================
# Configuration
# ============================================================================


class ConfigurationError(ZebTrackError):
    """Base exception for configuration errors.

    Raised when there are issues with application or project configuration,
    including invalid settings, missing required values, or schema errors.
    """

    pass


class SettingsError(ConfigurationError):
    """Error in settings validation or loading.

    Raised when application settings cannot be loaded, validated, or
    contain invalid values that prevent normal operation.
    """

    pass


class ProjectError(ConfigurationError):
    """Error in project configuration.

    Raised when project-specific configuration is invalid, missing required
    data, or contains values that prevent project operations.
    """

    pass


# ============================================================================
# Export for convenience
# ============================================================================

__all__ = [
    "AnalysisError",
    "ArduinoConnectionError",
    "ArduinoError",
    "CameraConnectionError",
    "CameraError",
    # Configuration
    "ConfigurationError",
    # Detection
    "DetectorError",
    # I/O
    "FileOperationError",
    "FrameProcessingError",
    # Hardware
    "HardwareError",
    "ModelError",
    "ModelLoadError",
    "ParquetError",
    # Processing
    "ProcessingError",
    "ProjectError",
    "RecorderError",
    "SettingsError",
    "TrackingError",
    # UI
    "UIError",
    "ValidationError",
    "VideoSourceError",
    "VideoWriteError",
    "WizardError",
    "ZebTrackError",
    "ZoneError",
]
