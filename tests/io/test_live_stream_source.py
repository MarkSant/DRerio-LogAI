"""
Tests for LiveStreamSource - time-limited camera wrapper for analysis.
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.io.live_stream_source import LiveStreamSource


@pytest.fixture
def mock_settings():
    """Create mock settings with camera configuration."""
    settings = MagicMock()
    settings.camera.index = 0
    settings.camera.desired_width = 640
    settings.camera.desired_height = 480
    settings.camera.max_reconnect_attempts = 10
    settings.camera.reconnect_timeout_seconds = 60.0
    settings.camera.max_frame_lag_ms = 500.0
    settings.video_processing.fps = 30.0
    return settings


class TestLiveStreamSourceInit:
    """Test LiveStreamSource initialization."""

    def test_init_requires_settings(self):
        """Test that settings_obj is required."""
        with pytest.raises(RuntimeError, match="Settings not injected"):
            LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=None)

    @patch("zebtrack.io.live_stream_source.Camera")
    def test_init_with_settings(self, mock_camera_class, mock_settings):
        """Test successful initialization with settings."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        stream = LiveStreamSource(camera_index=0, max_duration_s=300.0, settings_obj=mock_settings)

        assert stream.camera_index == 0
        assert stream.max_duration_s == 300.0
        assert stream.estimated_frame_count == int(300.0 * 30.0)  # duration * fps
        assert stream.width == 640
        assert stream.height == 480
        assert stream.fps == 30.0
        mock_camera_class.assert_called_once_with(settings_obj=mock_settings)

    @patch("zebtrack.io.live_stream_source.Camera")
    def test_init_calculates_estimated_frames(self, mock_camera_class, mock_settings):
        """Test that estimated frame count is calculated correctly."""
        mock_camera = MagicMock()
        mock_camera.actual_fps = 25.0
        mock_camera.actual_width = 1280
        mock_camera.actual_height = 720
        mock_camera_class.return_value = mock_camera

        stream = LiveStreamSource(camera_index=1, max_duration_s=120.0, settings_obj=mock_settings)

        assert stream.estimated_frame_count == int(120.0 * 25.0)  # 3000 frames


class TestLiveStreamSourceGetFrame:
    """Test frame retrieval with duration limits."""

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_frame_within_duration(self, mock_time, mock_camera_class, mock_settings):
        """Test getting frames within duration limit."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera.get_frame.return_value = (True, MagicMock())
        mock_camera_class.return_value = mock_camera

        # Mock time to simulate passage
        mock_time.time.side_effect = [100.0, 100.0, 101.0]  # start, get_frame, check

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        ret, frame = stream.get_frame()

        assert ret is True
        assert frame is not None
        assert stream.frame_number == 1
        mock_camera.get_frame.assert_called_once()

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_frame_exceeds_duration(self, mock_time, mock_camera_class, mock_settings):
        """Test that get_frame returns False when duration exceeded."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        # Mock time: start at 100, check at 115 (exceeds 10s limit)
        mock_time.time.side_effect = [100.0, 115.0]

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        ret, frame = stream.get_frame()

        assert ret is False
        assert frame is None
        mock_camera.get_frame.assert_not_called()

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_frame_increments_counter(self, mock_time, mock_camera_class, mock_settings):
        """Test that frame number increments correctly."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera.get_frame.return_value = (True, MagicMock())
        mock_camera_class.return_value = mock_camera

        # Always return early time
        mock_time.time.return_value = 100.0

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        assert stream.frame_number == 0

        stream.get_frame()
        assert stream.frame_number == 1

        stream.get_frame()
        assert stream.frame_number == 2

        stream.get_frame()
        assert stream.frame_number == 3


class TestLiveStreamSourceProperties:
    """Test property methods."""

    @patch("zebtrack.io.live_stream_source.Camera")
    def test_get_current_frame_number(self, mock_camera_class, mock_settings):
        """Test get_current_frame_number returns float."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        stream.frame_number = 42
        result = stream.get_current_frame_number()

        assert result == 42.0
        assert isinstance(result, float)

    @patch("zebtrack.io.live_stream_source.Camera")
    def test_get_properties(self, mock_camera_class, mock_settings):
        """Test get_properties returns correct dict."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 1280
        mock_camera.actual_height = 720
        mock_camera.actual_fps = 60.0
        mock_camera_class.return_value = mock_camera

        stream = LiveStreamSource(camera_index=2, max_duration_s=600.0, settings_obj=mock_settings)

        props = stream.get_properties()

        assert props["width"] == 1280
        assert props["height"] == 720
        assert props["fps"] == 60.0
        assert props["frame_count"] == int(600.0 * 60.0)
        assert props["camera_index"] == 2
        assert props["max_duration_s"] == 600.0
        assert props["is_live_stream"] is True

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_elapsed_time(self, mock_time, mock_camera_class, mock_settings):
        """Test elapsed time calculation."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        mock_time.time.side_effect = [100.0, 105.0]  # start, check

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        elapsed = stream.get_elapsed_time()
        assert elapsed == 5.0

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_remaining_time(self, mock_time, mock_camera_class, mock_settings):
        """Test remaining time calculation."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        mock_time.time.side_effect = [100.0, 107.0]  # start, check (7s elapsed)

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        remaining = stream.get_remaining_time()
        assert remaining == 3.0

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_get_remaining_time_never_negative(self, mock_time, mock_camera_class, mock_settings):
        """Test that remaining time is never negative."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        mock_time.time.side_effect = [100.0, 115.0]  # start, 15s elapsed (exceeds 10s)

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        remaining = stream.get_remaining_time()
        assert remaining == 0.0


class TestLiveStreamSourceRelease:
    """Test resource cleanup."""

    @patch("zebtrack.io.live_stream_source.Camera")
    @patch("zebtrack.io.live_stream_source.time")
    def test_release_calls_camera_release(self, mock_time, mock_camera_class, mock_settings):
        """Test that release properly cleans up camera."""
        mock_camera = MagicMock()
        mock_camera.actual_width = 640
        mock_camera.actual_height = 480
        mock_camera.actual_fps = 30.0
        mock_camera_class.return_value = mock_camera

        mock_time.time.side_effect = [100.0, 105.0]  # start, release

        stream = LiveStreamSource(camera_index=0, max_duration_s=10.0, settings_obj=mock_settings)

        stream.frame_number = 42
        stream.release()

        mock_camera.release.assert_called_once()
