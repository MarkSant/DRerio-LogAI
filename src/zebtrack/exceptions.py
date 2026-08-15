"""Public re-export of the DRerio LogAI exception hierarchy.

The classes themselves live in :mod:`zebtrack.core.exceptions`, which is the
single canonical definition. This module exists only so ``zebtrack.exceptions``
keeps working as an import path.

It used to declare its OWN copy of every class. That made
``zebtrack.exceptions.ValidationError`` and
``zebtrack.core.exceptions.ValidationError`` two unrelated types with the same
name, so ``except`` on one silently missed the other — the exact failure mode
this package's error boundaries are supposed to prevent. Re-exporting keeps one
class per name.

Exception Hierarchy:
    ZebTrackError (base)
    ├── FileOperationError
    │   ├── VideoNotFoundError
    │   ├── VideoReadError
    │   ├── VideoSourceError
    │   ├── VideoWriteError
    │   ├── CameraError
    │   │   ├── CameraNotFoundError
    │   │   ├── CameraAccessError
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
            ├── ProjectNotFoundError
            ├── ProjectLoadError
            ├── ProjectSaveError
            └── ProjectInvalidError

``CoordinatorError`` and its subclasses (``coordinators/base_coordinator.py``)
also inherit from ``ZebTrackError``, so a UI boundary that catches
``ZebTrackError`` catches coordinator failures too.
"""

from __future__ import annotations

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
    ProjectInvalidError,
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
