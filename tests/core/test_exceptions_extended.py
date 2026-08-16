"""
Extended unit tests for core exception hierarchy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.core.exceptions import (
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


class TestExceptionHierarchy:
    """Test that exception inheritance tree is correct."""

    def test_base_exception_hierarchy(self):
        assert issubclass(ZebTrackError, Exception)

    def test_file_operation_errors(self):
        assert issubclass(FileOperationError, ZebTrackError)
        assert issubclass(VideoNotFoundError, FileOperationError)
        assert issubclass(VideoReadError, FileOperationError)
        assert issubclass(VideoSourceError, FileOperationError)
        assert issubclass(VideoWriteError, FileOperationError)
        assert issubclass(CameraError, FileOperationError)
        assert issubclass(CameraConnectionError, CameraError)
        assert issubclass(RecorderError, FileOperationError)
        assert issubclass(ParquetError, FileOperationError)

    def test_detection_errors(self):
        assert issubclass(DetectorError, ZebTrackError)
        assert issubclass(ModelLoadError, DetectorError)
        assert issubclass(TrackingError, ZebTrackError)
        assert issubclass(ZoneError, ZebTrackError)

    def test_processing_errors(self):
        assert issubclass(ProcessingError, ZebTrackError)
        assert issubclass(FrameProcessingError, ProcessingError)
        assert issubclass(AnalysisError, ZebTrackError)

    def test_hardware_errors(self):
        assert issubclass(HardwareError, ZebTrackError)
        assert issubclass(ArduinoError, HardwareError)
        assert issubclass(ArduinoConnectionError, ArduinoError)

    def test_ui_errors(self):
        assert issubclass(UIError, ZebTrackError)
        assert issubclass(ValidationError, UIError)
        assert issubclass(WizardError, UIError)

    def test_configuration_errors(self):
        assert issubclass(ConfigurationError, ZebTrackError)
        assert issubclass(SettingsError, ConfigurationError)
        assert issubclass(ProjectError, ConfigurationError)
        assert issubclass(ProjectNotFoundError, ProjectError)
        assert issubclass(ProjectLoadError, ProjectError)
        assert issubclass(ProjectSaveError, ProjectError)
        assert issubclass(ProjectInvalidError, ProjectError)


class TestZebTrackErrorDetails:
    """Test ZebTrackError details dict behavior."""

    def test_details_default_empty(self):
        err = ZebTrackError("oops")
        assert err.details == {}

    def test_details_stored(self):
        err = ZebTrackError("bad", details={"code": 404})
        assert err.details["code"] == 404

    def test_can_catch_as_base(self):
        with pytest.raises(ZebTrackError):
            raise VideoNotFoundError("missing.mp4")


class TestProjectInvalidError:
    """Test ProjectInvalidError structured error."""

    def test_message_stored(self):
        err = ProjectInvalidError("Project corrupt")
        assert "Project corrupt" in str(err)

    def test_path_coerced_to_path(self):
        err = ProjectInvalidError("bad", path="/some/path")
        assert err.path == Path("/some/path")

    def test_path_none(self):
        err = ProjectInvalidError("bad")
        assert err.path is None

    def test_cause_stored(self):
        cause = ValueError("inner")
        err = ProjectInvalidError("bad", cause=cause)
        assert err.cause is cause

    def test_details_forwarded(self):
        err = ProjectInvalidError("bad", details={"hint": "check file"})
        assert err.details["hint"] == "check file"
