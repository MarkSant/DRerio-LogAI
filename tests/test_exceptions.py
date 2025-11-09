"""Tests for custom exception hierarchy."""

import pytest

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


class TestBaseException:
    """Test the base ZebTrackError exception."""

    def test_base_exception_instantiation(self):
        """Test that ZebTrackError can be instantiated with a message."""
        exc = ZebTrackError("Base error message")
        assert str(exc) == "Base error message"

    def test_base_exception_raising(self):
        """Test that ZebTrackError can be raised and caught."""
        with pytest.raises(ZebTrackError):
            raise ZebTrackError("Test error")

    def test_base_exception_inherits_from_exception(self):
        """Test that ZebTrackError inherits from Exception."""
        assert issubclass(ZebTrackError, Exception)


class TestExceptionHierarchy:
    """Test exception inheritance structure."""

    def test_all_domain_exceptions_inherit_from_zebtrack_error(self):
        """Test that all domain base exceptions inherit from ZebTrackError."""
        domain_bases = [
            FileOperationError,
            DetectorError,
            TrackingError,
            ZoneError,
            ProcessingError,
            AnalysisError,
            HardwareError,
            UIError,
            ConfigurationError,
        ]

        for exc_class in domain_bases:
            assert issubclass(exc_class, ZebTrackError), (
                f"{exc_class.__name__} does not inherit from ZebTrackError"
            )

    def test_file_operation_exceptions_hierarchy(self):
        """Test I/O exception inheritance."""
        assert issubclass(VideoSourceError, FileOperationError)
        assert issubclass(VideoWriteError, FileOperationError)
        assert issubclass(CameraError, FileOperationError)
        assert issubclass(CameraConnectionError, CameraError)
        assert issubclass(CameraConnectionError, FileOperationError)
        assert issubclass(RecorderError, FileOperationError)
        assert issubclass(ParquetError, FileOperationError)

    def test_detector_exceptions_hierarchy(self):
        """Test detector exception inheritance."""
        assert issubclass(ModelLoadError, DetectorError)
        assert issubclass(ModelError, DetectorError)

    def test_processing_exceptions_hierarchy(self):
        """Test processing exception inheritance."""
        assert issubclass(FrameProcessingError, ProcessingError)

    def test_hardware_exceptions_hierarchy(self):
        """Test hardware exception inheritance."""
        assert issubclass(ArduinoError, HardwareError)
        assert issubclass(ArduinoConnectionError, ArduinoError)
        assert issubclass(ArduinoConnectionError, HardwareError)

    def test_ui_exceptions_hierarchy(self):
        """Test UI exception inheritance."""
        assert issubclass(ValidationError, UIError)
        assert issubclass(WizardError, UIError)

    def test_configuration_exceptions_hierarchy(self):
        """Test configuration exception inheritance."""
        assert issubclass(SettingsError, ConfigurationError)
        assert issubclass(ProjectError, ConfigurationError)

    def test_all_exceptions_inherit_from_zebtrack_error(self):
        """Test that ALL exceptions ultimately inherit from ZebTrackError."""
        all_exceptions = [
            # I/O
            FileOperationError,
            VideoSourceError,
            VideoWriteError,
            CameraError,
            CameraConnectionError,
            RecorderError,
            ParquetError,
            # Detection
            DetectorError,
            ModelLoadError,
            ModelError,
            TrackingError,
            ZoneError,
            # Processing
            ProcessingError,
            FrameProcessingError,
            AnalysisError,
            # Hardware
            HardwareError,
            ArduinoError,
            ArduinoConnectionError,
            # UI
            UIError,
            ValidationError,
            WizardError,
            # Configuration
            ConfigurationError,
            SettingsError,
            ProjectError,
        ]

        for exc_class in all_exceptions:
            assert issubclass(exc_class, ZebTrackError), (
                f"{exc_class.__name__} does not inherit from ZebTrackError"
            )


class TestExceptionInstantiation:
    """Test that all exceptions can be instantiated with messages."""

    def test_file_operation_exceptions(self):
        """Test I/O exception instantiation."""
        exc = VideoSourceError("Cannot open video file")
        assert str(exc) == "Cannot open video file"

        exc = CameraConnectionError("Camera index 0 not found")
        assert str(exc) == "Camera index 0 not found"

        exc = ParquetError("Invalid schema")
        assert str(exc) == "Invalid schema"

    def test_detector_exceptions(self):
        """Test detector exception instantiation."""
        exc = ModelLoadError("Model file not found: model.pt")
        assert str(exc) == "Model file not found: model.pt"

        exc = ModelError("Inference failed on frame 100")
        assert str(exc) == "Inference failed on frame 100"

    def test_processing_exceptions(self):
        """Test processing exception instantiation."""
        exc = FrameProcessingError("Failed to decode frame 42")
        assert str(exc) == "Failed to decode frame 42"

        exc = AnalysisError("ROI analysis failed")
        assert str(exc) == "ROI analysis failed"

    def test_hardware_exceptions(self):
        """Test hardware exception instantiation."""
        exc = ArduinoConnectionError("Arduino not found on COM3")
        assert str(exc) == "Arduino not found on COM3"

    def test_ui_exceptions(self):
        """Test UI exception instantiation."""
        exc = ValidationError("Invalid frame rate: must be > 0")
        assert str(exc) == "Invalid frame rate: must be > 0"

        exc = WizardError("Cannot proceed to step 3: missing required data")
        assert str(exc) == "Cannot proceed to step 3: missing required data"

    def test_configuration_exceptions(self):
        """Test configuration exception instantiation."""
        exc = SettingsError("Invalid configuration: missing camera.index")
        assert str(exc) == "Invalid configuration: missing camera.index"

        exc = ProjectError("Project data corrupted")
        assert str(exc) == "Project data corrupted"


class TestExceptionRaising:
    """Test that exceptions can be raised and caught properly."""

    def test_catch_specific_exception(self):
        """Test catching specific exception types."""
        with pytest.raises(VideoSourceError):
            raise VideoSourceError("Video error")

        with pytest.raises(ModelLoadError):
            raise ModelLoadError("Model error")

        with pytest.raises(ValidationError):
            raise ValidationError("Validation error")

    def test_catch_base_class(self):
        """Test that exceptions can be caught by their base class."""
        # Catch by immediate parent
        with pytest.raises(FileOperationError):
            raise VideoSourceError("Video error")

        with pytest.raises(DetectorError):
            raise ModelLoadError("Model error")

        with pytest.raises(UIError):
            raise ValidationError("Validation error")

    def test_catch_zebtrack_error_base(self):
        """Test that all exceptions can be caught by ZebTrackError."""
        with pytest.raises(ZebTrackError):
            raise VideoSourceError("I/O error")

        with pytest.raises(ZebTrackError):
            raise ModelError("Detection error")

        with pytest.raises(ZebTrackError):
            raise ArduinoConnectionError("Hardware error")

        with pytest.raises(ZebTrackError):
            raise ValidationError("UI error")

        with pytest.raises(ZebTrackError):
            raise SettingsError("Config error")

    def test_exception_chaining(self):
        """Test exception chaining with 'from' clause."""
        original_error = ValueError("Original error")

        with pytest.raises(VideoSourceError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise VideoSourceError("Cannot open video") from e

        assert exc_info.value.__cause__ is original_error

    def test_nested_exception_catching(self):
        """Test catching nested exceptions at different levels."""
        # Should catch CameraConnectionError specifically
        with pytest.raises(CameraConnectionError):
            raise CameraConnectionError("Specific error")

        # Should catch by parent CameraError
        with pytest.raises(CameraError):
            raise CameraConnectionError("Parent catch")

        # Should catch by grandparent FileOperationError
        with pytest.raises(FileOperationError):
            raise CameraConnectionError("Grandparent catch")

        # Should catch by root ZebTrackError
        with pytest.raises(ZebTrackError):
            raise CameraConnectionError("Root catch")


class TestExceptionMessages:
    """Test exception message handling."""

    def test_exception_without_message(self):
        """Test that exceptions can be raised without a message."""
        exc = ZebTrackError()
        assert str(exc) == ""

    def test_exception_with_empty_message(self):
        """Test that exceptions can have empty messages."""
        exc = VideoSourceError("")
        assert str(exc) == ""

    def test_exception_with_multiline_message(self):
        """Test that exceptions can handle multiline messages."""
        message = "Error details:\n  - Line 1\n  - Line 2"
        exc = AnalysisError(message)
        assert str(exc) == message

    def test_exception_with_formatted_message(self):
        """Test that exceptions work with formatted strings."""
        frame_num = 42
        exc = FrameProcessingError(f"Failed at frame {frame_num}")
        assert str(exc) == "Failed at frame 42"


class TestExceptionUseCases:
    """Test realistic exception usage scenarios."""

    def test_file_not_found_scenario(self):
        """Test handling of file not found scenario."""

        def load_video(path):
            if not path:
                raise VideoSourceError(f"Video file not found: {path}")

        with pytest.raises(VideoSourceError) as exc_info:
            load_video("")

        assert "not found" in str(exc_info.value)

    def test_model_loading_scenario(self):
        """Test handling of model loading failure."""

        def load_model(model_path):
            if model_path.endswith(".invalid"):
                raise ModelLoadError(f"Unsupported model format: {model_path}")

        with pytest.raises(ModelLoadError) as exc_info:
            load_model("model.invalid")

        assert "Unsupported" in str(exc_info.value)

    def test_validation_scenario(self):
        """Test input validation failure."""

        def validate_fps(fps):
            if fps <= 0:
                raise ValidationError(f"FPS must be positive, got {fps}")

        with pytest.raises(ValidationError) as exc_info:
            validate_fps(-10)

        assert "positive" in str(exc_info.value)

    def test_hardware_connection_scenario(self):
        """Test hardware connection failure."""

        def connect_arduino(port):
            if port is None:
                raise ArduinoConnectionError("No Arduino port specified")

        with pytest.raises(ArduinoConnectionError):
            connect_arduino(None)

        # Should also be catchable as HardwareError
        with pytest.raises(HardwareError):
            connect_arduino(None)

    def test_catching_all_zebtrack_errors(self):
        """Test catching all application errors with ZebTrackError."""
        errors_to_test = [
            VideoSourceError("Video error"),
            ModelLoadError("Model error"),
            ValidationError("Validation error"),
            ArduinoError("Hardware error"),
            SettingsError("Config error"),
        ]

        for error in errors_to_test:
            with pytest.raises(ZebTrackError):
                raise error


class TestExceptionDocstrings:
    """Test that all exceptions have proper documentation."""

    def test_all_exceptions_have_docstrings(self):
        """Test that all exception classes have docstrings."""
        exceptions = [
            ZebTrackError,
            FileOperationError,
            VideoSourceError,
            VideoWriteError,
            CameraError,
            CameraConnectionError,
            RecorderError,
            ParquetError,
            DetectorError,
            ModelLoadError,
            ModelError,
            TrackingError,
            ZoneError,
            ProcessingError,
            FrameProcessingError,
            AnalysisError,
            HardwareError,
            ArduinoError,
            ArduinoConnectionError,
            UIError,
            ValidationError,
            WizardError,
            ConfigurationError,
            SettingsError,
            ProjectError,
        ]

        for exc_class in exceptions:
            assert exc_class.__doc__ is not None, (
                f"{exc_class.__name__} is missing a docstring"
            )
            assert len(exc_class.__doc__.strip()) > 0, (
                f"{exc_class.__name__} has an empty docstring"
            )
