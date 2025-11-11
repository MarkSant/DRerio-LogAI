"""
Tests for FrameSourceFactory - unified video/camera source creation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.io.frame_source_factory import FrameSourceFactory


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.camera.index = 0
    settings.camera.desired_width = 640
    settings.camera.desired_height = 480
    return settings


class TestFrameSourceFactoryFromPath:
    """Test creating VideoFileSource from file paths."""

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    def test_create_from_existing_file(self, mock_video_class, tmp_path):
        """Test creating source from existing video file."""
        video_file = tmp_path / "test.mp4"
        video_file.touch()

        mock_video = MagicMock()
        mock_video_class.return_value = mock_video

        result = FrameSourceFactory.create_from_path(video_file)

        assert result == mock_video
        mock_video_class.assert_called_once_with(video_file)

    def test_create_from_nonexistent_file(self):
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            FrameSourceFactory.create_from_path("nonexistent.mp4")

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    def test_create_from_string_path(self, mock_video_class, tmp_path):
        """Test creating from string path (converts to Path)."""
        video_file = tmp_path / "video.avi"
        video_file.touch()

        mock_video = MagicMock()
        mock_video_class.return_value = mock_video

        result = FrameSourceFactory.create_from_path(str(video_file))

        assert result == mock_video
        # Verify it was converted to Path
        call_arg = mock_video_class.call_args[0][0]
        assert isinstance(call_arg, Path)


class TestFrameSourceFactoryFromCamera:
    """Test creating Camera/LiveStreamSource from camera index."""

    @patch("zebtrack.io.frame_source_factory.LiveStreamSource")
    def test_create_with_duration_limit(self, mock_live_class, mock_settings):
        """Test creating LiveStreamSource when duration specified."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        result = FrameSourceFactory.create_from_camera(
            camera_index=0, max_duration_s=300.0, settings_obj=mock_settings
        )

        assert result == mock_live
        mock_live_class.assert_called_once_with(
            camera_index=0, max_duration_s=300.0, settings_obj=mock_settings
        )

    @patch("zebtrack.io.camera.Camera")
    def test_create_without_duration_limit(self, mock_camera_class, mock_settings):
        """Test creating Camera when no duration specified."""
        mock_camera = MagicMock()
        mock_camera_class.return_value = mock_camera

        result = FrameSourceFactory.create_from_camera(
            camera_index=1, max_duration_s=None, settings_obj=mock_settings
        )

        assert result == mock_camera
        # Camera is called with a copy of settings (model_copy)
        mock_camera_class.assert_called_once()
        assert "settings_obj" in mock_camera_class.call_args.kwargs

    @patch("zebtrack.io.camera.Camera")
    def test_create_with_zero_duration(self, mock_camera_class, mock_settings):
        """Test creating Camera when duration is 0 (unlimited)."""
        mock_camera = MagicMock()
        mock_camera_class.return_value = mock_camera

        result = FrameSourceFactory.create_from_camera(
            camera_index=0, max_duration_s=0, settings_obj=mock_settings
        )

        assert result == mock_camera

    def test_create_camera_without_settings(self):
        """Test error when settings not provided for camera."""
        with pytest.raises(RuntimeError, match="settings_obj required"):
            FrameSourceFactory.create_from_camera(camera_index=0, settings_obj=None)


class TestFrameSourceFactoryCreate:
    """Test unified create() method."""

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    def test_create_from_path_object(self, mock_video_class, tmp_path):
        """Test create() with Path object."""
        video_file = tmp_path / "video.mp4"
        video_file.touch()

        mock_video = MagicMock()
        mock_video_class.return_value = mock_video

        result = FrameSourceFactory.create(video_file)

        assert result == mock_video

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    def test_create_from_string_path(self, mock_video_class, tmp_path):
        """Test create() with string path."""
        video_file = tmp_path / "video.mkv"
        video_file.touch()

        mock_video = MagicMock()
        mock_video_class.return_value = mock_video

        result = FrameSourceFactory.create(str(video_file))

        assert result == mock_video

    @patch("zebtrack.io.camera.Camera")
    def test_create_from_integer(self, mock_camera_class, mock_settings):
        """Test create() with integer camera index."""
        mock_camera = MagicMock()
        mock_camera_class.return_value = mock_camera

        result = FrameSourceFactory.create(0, settings_obj=mock_settings)

        assert result == mock_camera

    @patch("zebtrack.io.camera.Camera")
    def test_create_from_dict_camera(self, mock_camera_class, mock_settings):
        """Test create() with camera dict config."""
        mock_camera = MagicMock()
        mock_camera_class.return_value = mock_camera

        config = {"type": "camera", "index": 1}

        result = FrameSourceFactory.create(config, settings_obj=mock_settings)

        assert result == mock_camera

    @patch("zebtrack.io.frame_source_factory.LiveStreamSource")
    def test_create_from_dict_camera_with_duration(self, mock_live_class, mock_settings):
        """Test create() with camera dict including duration."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        config = {"type": "camera", "index": 0, "max_duration_s": 120.0}

        result = FrameSourceFactory.create(config, settings_obj=mock_settings)

        assert result == mock_live
        mock_live_class.assert_called_once_with(
            camera_index=0, max_duration_s=120.0, settings_obj=mock_settings
        )

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    def test_create_from_dict_file(self, mock_video_class, tmp_path):
        """Test create() with file dict config."""
        video_file = tmp_path / "test.mp4"
        video_file.touch()

        mock_video = MagicMock()
        mock_video_class.return_value = mock_video

        config = {"type": "file", "path": str(video_file)}

        result = FrameSourceFactory.create(config)

        assert result == mock_video

    def test_create_dict_missing_path(self):
        """Test error when file dict missing path key."""
        config = {"type": "file"}

        with pytest.raises(ValueError, match="requires 'path' key"):
            FrameSourceFactory.create(config)

    def test_create_dict_invalid_type(self):
        """Test error with invalid source type in dict."""
        config = {"type": "invalid_type"}

        with pytest.raises(ValueError, match="Invalid source type.*'invalid_type'"):
            FrameSourceFactory.create(config)

    def test_create_invalid_source_type(self):
        """Test error with completely invalid source type."""
        with pytest.raises(ValueError, match="Invalid source type"):
            FrameSourceFactory.create(123.456)  # Float not supported

    def test_create_list_not_supported(self):
        """Test that list is not a valid source type."""
        with pytest.raises(ValueError, match="Invalid source type"):
            FrameSourceFactory.create([1, 2, 3])


class TestFrameSourceFactoryIntegration:
    """Integration-style tests with multiple source types."""

    @patch("zebtrack.io.frame_source_factory.VideoFileSource")
    @patch("zebtrack.io.frame_source_factory.LiveStreamSource")
    def test_create_multiple_types(
        self, mock_live_class, mock_video_class, tmp_path, mock_settings
    ):
        """Test creating different source types in sequence."""
        # Setup mocks
        video_file = tmp_path / "video.mp4"
        video_file.touch()

        mock_video = MagicMock()
        mock_live = MagicMock()
        mock_video_class.return_value = mock_video
        mock_live_class.return_value = mock_live

        # Create video source
        result1 = FrameSourceFactory.create(video_file)
        assert result1 == mock_video

        # Create live stream source
        result2 = FrameSourceFactory.create(
            {"type": "camera", "index": 0, "max_duration_s": 60.0}, settings_obj=mock_settings
        )
        assert result2 == mock_live

        # Verify both were called
        assert mock_video_class.call_count == 1
        assert mock_live_class.call_count == 1
