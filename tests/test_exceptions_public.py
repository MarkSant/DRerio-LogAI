"""Tests for zebtrack.exceptions public exception hierarchy."""

from __future__ import annotations

import pytest

import zebtrack.exceptions as public_exceptions

ALL_EXCEPTIONS = [
    public_exceptions.ZebTrackError,
    public_exceptions.FileOperationError,
    public_exceptions.VideoSourceError,
    public_exceptions.VideoWriteError,
    public_exceptions.CameraError,
    public_exceptions.CameraConnectionError,
    public_exceptions.RecorderError,
    public_exceptions.ParquetError,
    public_exceptions.DetectorError,
    public_exceptions.ModelLoadError,
    public_exceptions.ModelError,
    public_exceptions.TrackingError,
    public_exceptions.ZoneError,
    public_exceptions.ProcessingError,
    public_exceptions.FrameProcessingError,
    public_exceptions.AnalysisError,
    public_exceptions.HardwareError,
    public_exceptions.ArduinoError,
    public_exceptions.ArduinoConnectionError,
    public_exceptions.UIError,
    public_exceptions.ValidationError,
    public_exceptions.WizardError,
    public_exceptions.ConfigurationError,
    public_exceptions.SettingsError,
    public_exceptions.ProjectError,
]


@pytest.mark.parametrize("exc_class", ALL_EXCEPTIONS)
def test_public_exceptions_are_exception_subclasses(exc_class: type[Exception]) -> None:
    """All public exceptions should inherit from Exception and ZebTrackError."""
    assert issubclass(exc_class, Exception)
    assert issubclass(exc_class, public_exceptions.ZebTrackError)


@pytest.mark.parametrize("exc_class", ALL_EXCEPTIONS)
def test_public_exceptions_instantiation(exc_class: type[Exception]) -> None:
    """All public exceptions should be instantiable with a message."""
    message = f"Test message for {exc_class.__name__}"
    exc = exc_class(message)
    assert str(exc) == message


def test_public_exceptions_all_exports_are_valid() -> None:
    """Every name in __all__ should resolve to an exception class."""
    for name in public_exceptions.__all__:
        obj = getattr(public_exceptions, name)
        assert isinstance(obj, type), f"{name} is not a class"
        assert issubclass(obj, Exception), f"{name} is not an Exception subclass"


def test_public_exception_hierarchy() -> None:
    """Verify a few key inheritance relationships."""
    assert issubclass(public_exceptions.VideoSourceError, public_exceptions.FileOperationError)
    assert issubclass(public_exceptions.CameraConnectionError, public_exceptions.CameraError)
    assert issubclass(public_exceptions.ModelLoadError, public_exceptions.DetectorError)
    assert issubclass(public_exceptions.FrameProcessingError, public_exceptions.ProcessingError)
    assert issubclass(public_exceptions.ArduinoConnectionError, public_exceptions.ArduinoError)
    assert issubclass(public_exceptions.ValidationError, public_exceptions.UIError)
    assert issubclass(public_exceptions.ProjectError, public_exceptions.ConfigurationError)
