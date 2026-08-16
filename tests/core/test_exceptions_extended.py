"""Extended unit tests for core/exceptions.py custom exception hierarchy."""

from __future__ import annotations

from pathlib import Path

import pytest

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


class TestExceptionsExtended:
    """Test full exception inheritance hierarchy and custom constructor fields."""

    def test_base_zebtrack_error_with_details(self):
        err = ZebTrackError("base failure", details={"step": 1, "code": "E001"})
        assert str(err) == "base failure"
        assert err.details == {"step": 1, "code": "E001"}

    def test_base_zebtrack_error_default_details(self):
        err = ZebTrackError("simple failure")
        assert err.details == {}

    def test_file_operation_error_hierarchy(self):
        for exc_cls in [
            VideoNotFoundError,
            VideoReadError,
            VideoSourceError,
            VideoWriteError,
            CameraError,
            CameraNotFoundError,
            CameraAccessError,
            CameraConnectionError,
            RecorderError,
            ParquetError,
        ]:
            instance = exc_cls("file op error")
            assert isinstance(instance, FileOperationError)
            assert isinstance(instance, ZebTrackError)

    def test_camera_error_hierarchy(self):
        for exc_cls in [CameraNotFoundError, CameraAccessError, CameraConnectionError]:
            instance = exc_cls("camera error")
            assert isinstance(instance, CameraError)
            assert isinstance(instance, FileOperationError)

    def test_detector_error_hierarchy(self):
        for exc_cls in [ModelLoadError, ModelError]:
            instance = exc_cls("detector error")
            assert isinstance(instance, DetectorError)
            assert isinstance(instance, ZebTrackError)

        assert issubclass(TrackingError, ZebTrackError)
        assert issubclass(ZoneError, ZebTrackError)

    def test_processing_error_hierarchy(self):
        for exc_cls in [FrameProcessingError]:
            instance = exc_cls("processing error")
            assert isinstance(instance, ProcessingError)
            assert isinstance(instance, ZebTrackError)

        assert issubclass(AnalysisError, ZebTrackError)

    def test_hardware_error_hierarchy(self):
        instance = ArduinoConnectionError("arduino connect failure")
        assert isinstance(instance, ArduinoError)
        assert isinstance(instance, HardwareError)
        assert isinstance(instance, ZebTrackError)

    def test_ui_error_hierarchy(self):
        for exc_cls in [ValidationError, WizardError]:
            instance = exc_cls("ui error")
            assert isinstance(instance, UIError)
            assert isinstance(instance, ZebTrackError)

    def test_configuration_error_hierarchy(self):
        for exc_cls in [
            SettingsError,
            ProjectError,
            ProjectNotFoundError,
            ProjectLoadError,
            ProjectSaveError,
            ProjectInvalidError,
        ]:
            instance = exc_cls("config error")
            assert isinstance(instance, ConfigurationError)
            assert isinstance(instance, ZebTrackError)

    def test_project_invalid_error_full_constructor(self):
        cause_exc = OSError("Disk read failure")
        err = ProjectInvalidError(
            "Project structure invalid",
            path="C:/Projects/test_proj",
            cause=cause_exc,
            details={"corrupted_file": "meta.json"},
        )
        assert str(err) == "Project structure invalid"
        assert err.path == Path("C:/Projects/test_proj")
        assert err.cause is cause_exc
        assert err.details == {"corrupted_file": "meta.json"}

    def test_project_invalid_error_path_none(self):
        err = ProjectInvalidError("Invalid project", path=None)
        assert err.path is None
        assert err.cause is None

    def test_project_invalid_error_path_already_path_instance(self):
        p = Path("C:/Projects/exp1")
        err = ProjectInvalidError("Error with path", path=p)
        assert err.path == p

    def test_raising_and_catching_custom_exceptions(self):
        with pytest.raises(ZebTrackError, match="Video not found"):
            raise VideoNotFoundError("Video not found at path")

        with pytest.raises(ProjectError, match="Cannot save"):
            raise ProjectSaveError("Cannot save project")
