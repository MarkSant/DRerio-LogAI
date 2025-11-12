"""Comprehensive tests for io/sources.py."""

from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.controller_factory import create_mock_settings
from zebtrack.io.camera import Camera
from zebtrack.io.sources import create_source
from zebtrack.io.video_source import VideoFileSource


def test_create_source_camera():
    """Test creating a camera source."""
    settings = create_mock_settings()
    # Mock cv2.VideoCapture to avoid opening real camera
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cap:
        mock_cap.return_value.isOpened.return_value = True
        mock_cap.return_value.read.return_value = (True, MagicMock())
        source = create_source("camera", settings_obj=settings)
        assert isinstance(source, Camera)


def test_create_source_camera_missing_settings():
    """Test that ValueError is raised when settings_obj is missing for camera source."""
    with pytest.raises(ValueError, match="`settings_obj` keyword argument is required"):
        create_source("camera")


def test_create_source_file(tmp_path):
    """Test creating a file source."""
    # Create a dummy video file path
    video_path = str(tmp_path / "test_video.mp4")

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        source = create_source("file", video_path=video_path)

        # Verify VideoFileSource was called with correct path
        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance


def test_create_source_file_missing_video_path():
    """Test that ValueError is raised when video_path is missing for file source."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file")


def test_create_source_file_invalid_video_path_type():
    """Test that ValueError is raised when video_path is not a string."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file", video_path=123)  # type: ignore[arg-type]


def test_create_source_file_none_video_path():
    """Test that ValueError is raised when video_path is None."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file", video_path=None)


def test_create_source_file_empty_video_path():
    """Test that ValueError is raised when video_path is empty string."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file", video_path="")


def test_create_source_unsupported_type():
    """Test that ValueError is raised for unsupported source type."""
    with pytest.raises(ValueError, match="Unsupported source type: invalid"):
        create_source("invalid")


def test_create_source_case_sensitive():
    """Test that source_type is case-sensitive."""
    with pytest.raises(ValueError, match="Unsupported source type: CAMERA"):
        create_source("CAMERA")

    with pytest.raises(ValueError, match="Unsupported source type: File"):
        create_source("File", video_path="test.mp4")


def test_create_source_file_with_extra_kwargs(tmp_path):
    """Test that extra kwargs don't break file source creation."""
    video_path = str(tmp_path / "test_video.mp4")

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        # Extra kwargs should be ignored
        source = create_source("file", video_path=video_path, extra_param="ignored")

        # Verify VideoFileSource was called with only video_path (extra_param ignored)
        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance


def test_create_source_camera_ignores_extra_kwargs():
    """Test that extra kwargs are ignored for camera source."""
    settings = create_mock_settings()
    # Mock cv2.VideoCapture to avoid opening real camera
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cap:
        mock_cap.return_value.isOpened.return_value = True
        mock_cap.return_value.read.return_value = (True, MagicMock())
        # Extra kwargs should be ignored
        source = create_source("camera", settings_obj=settings, extra_param="ignored")
        assert isinstance(source, Camera)


def test_create_source_file_with_special_characters(tmp_path):
    """Test creating file source with path containing special characters."""
    video_path = str(tmp_path / "test video (1).mp4")

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        source = create_source("file", video_path=video_path)

        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance


def test_create_source_file_with_unicode(tmp_path):
    """Test creating file source with path containing unicode characters."""
    video_path = str(tmp_path / "vídeo_тест_测试.mp4")

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        source = create_source("file", video_path=video_path)

        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance


def test_create_source_returns_frame_source_interface():
    """Test that all returned sources implement FrameSource interface."""
    settings = create_mock_settings()
    # Mock cv2.VideoCapture to avoid opening real camera
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cap:
        mock_cap.return_value.isOpened.return_value = True
        mock_cap.return_value.read.return_value = (True, MagicMock())
        # Test camera
        camera = create_source("camera", settings_obj=settings)
        assert hasattr(camera, "get_frame")
        assert hasattr(camera, "release")
        assert hasattr(camera, "get_properties")

    # Test file (note: VideoFileSource validates file existence in __init__)
    # So we just verify the interface would exist
    assert hasattr(VideoFileSource, "get_frame")
    assert hasattr(VideoFileSource, "release")
    assert hasattr(VideoFileSource, "get_properties")


def test_create_source_supported_types_documentation():
    """Test that error message lists supported types."""
    with pytest.raises(ValueError, match="Supported types are 'camera', 'file'"):
        create_source("unsupported")


def test_create_source_file_absolute_path(tmp_path):
    """Test creating file source with absolute path."""
    video_path = str(tmp_path.absolute() / "test_video.mp4")

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        source = create_source("file", video_path=video_path)

        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance


def test_create_source_file_relative_path():
    """Test creating file source with relative path."""
    video_path = "./test_video.mp4"

    # Mock VideoFileSource to avoid file existence validation
    with patch("zebtrack.io.sources.VideoFileSource") as mock_video:
        mock_instance = MagicMock(spec=VideoFileSource)
        mock_video.return_value = mock_instance

        source = create_source("file", video_path=video_path)

        mock_video.assert_called_once_with(video_path=video_path)
        assert source == mock_instance
