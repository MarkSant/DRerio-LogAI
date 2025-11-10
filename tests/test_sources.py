import os
import time
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from zebtrack.io import Camera, FrameSource, VideoFileSource, create_source


@pytest.fixture
def dummy_video_file():
    """A pytest fixture to create a temporary video file for testing."""
    video_path = "test_video.avi"
    width, height = 64, 48
    fps = 10
    frame_count = 5
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")

    writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        pytest.fail("Could not open dummy video writer.")

    # Write unique frames
    for i in range(frame_count):
        frame = np.full((height, width, 3), i, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    # Yield test parameters
    yield video_path, width, height, fps, frame_count

    # Teardown
    if os.path.exists(video_path):
        os.remove(video_path)


def test_video_file_source_init_success(dummy_video_file):
    """Tests successful initialization and property retrieval."""
    video_path, width, height, fps, frame_count = dummy_video_file
    source = VideoFileSource(video_path)
    assert isinstance(source, FrameSource)

    props = source.get_properties()
    assert props["width"] == width
    assert props["height"] == height
    # Note: FPS from cv2 can sometimes be imprecise, so we check within a range
    assert abs(props["fps"] - fps) < 0.1
    assert props["frame_count"] == frame_count
    source.release()


def test_video_file_source_file_not_found():
    """Tests that initializing with a bad path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        VideoFileSource("non_existent_file.mp4")


def test_video_file_source_read_frames_and_eos(dummy_video_file):
    """Tests frame reading and verifies the end-of-stream condition."""
    video_path, _, _, _, frame_count = dummy_video_file
    source = VideoFileSource(video_path)

    frames_read = 0
    while True:
        ret, frame = source.get_frame()
        if not ret:
            break
        frames_read += 1
        assert isinstance(frame, np.ndarray)
        # Check that the frame content is as expected
        expected_value = frames_read - 1
        assert np.all(frame == expected_value)

    assert frames_read == frame_count

    # After the loop, test that get_frame continues to signal end-of-stream
    ret_eos, frame_eos = source.get_frame()
    assert not ret_eos
    assert frame_eos is None
    source.release()


# --- Tests for the factory function ---


def test_create_source_for_file(dummy_video_file):
    """Tests that the factory function can create a VideoFileSource."""
    video_path, _, _, _, _ = dummy_video_file
    source = create_source("file", video_path=video_path)
    assert isinstance(source, VideoFileSource)
    ret, frame = source.get_frame()
    assert ret
    assert frame is not None
    source.release()


def test_create_source_invalid_type():
    """Tests that the factory raises an error for an unknown source type."""
    with pytest.raises(ValueError, match="Unsupported source type"):
        create_source("invalid_source_type")


def test_create_source_file_missing_kwarg():
    """Tests that the factory raises an error if video_path is missing."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file")


def test_create_source_file_wrong_kwarg_type():
    """Tests that the factory raises an error if video_path is not a string."""
    with pytest.raises(ValueError, match="`video_path` keyword argument is required"):
        create_source("file", video_path=123)


# --- Tests for Camera class ---


@pytest.fixture
def mock_video_capture(monkeypatch):
    """A pytest fixture to mock cv2.VideoCapture and settings."""
    # Mock settings for Camera
    mock_settings = MagicMock()
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 640
    mock_settings.camera.desired_height = 480
    mock_settings.camera.max_reconnect_attempts = 10
    mock_settings.camera.reconnect_timeout_seconds = 30.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    mock_settings.video_processing.fps = 30.0

    # Patch Camera.__init__ to inject mock settings
    original_init = Camera.__init__

    def patched_init(self, settings_obj=None):
        return original_init(self, settings_obj=mock_settings)

    monkeypatch.setattr(Camera, "__init__", patched_init)

    mock_cap_instance = MagicMock()
    # Mock isOpened() as a method that returns True
    mock_cap_instance.isOpened.return_value = True
    mock_cap_instance.get.side_effect = [640, 480, 30.0]
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap_instance.read.return_value = (True, dummy_frame)
    mock_cap_class = MagicMock(return_value=mock_cap_instance)
    monkeypatch.setattr(cv2, "VideoCapture", mock_cap_class)
    yield mock_cap_instance


def test_camera_init_success(mock_video_capture):
    """Tests that the Camera class initializes correctly with a mock device."""
    camera = Camera()
    assert isinstance(camera, FrameSource)
    # Check that the underlying cv2.VideoCapture was called
    cv2.VideoCapture.assert_called_once()
    camera.release()


def test_camera_init_failure(monkeypatch):
    """Tests that the Camera class raises IOError if the device fails to open."""
    # Mock settings for Camera
    mock_settings = MagicMock()
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 640
    mock_settings.camera.desired_height = 480
    mock_settings.camera.max_reconnect_attempts = 10
    mock_settings.camera.reconnect_timeout_seconds = 30.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    mock_settings.video_processing.fps = 30.0

    mock_cap_instance = MagicMock()
    # Mock isOpened() as a method that returns False
    mock_cap_instance.isOpened.return_value = False
    mock_cap_class = MagicMock(return_value=mock_cap_instance)
    monkeypatch.setattr(cv2, "VideoCapture", mock_cap_class)

    with pytest.raises(IOError):
        Camera(settings_obj=mock_settings)


def test_camera_get_frame_non_blocking(mock_video_capture):
    """Tests that get_frame returns a frame from the threaded reader."""
    camera = Camera()
    # Give the thread a moment to read the first frame
    time.sleep(0.1)

    ret, frame = camera.get_frame()
    assert ret
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (480, 640, 3)

    # Check that read was called in the background
    mock_video_capture.read.assert_called()
    camera.release()


def test_camera_release_stops_thread_and_releases_device(mock_video_capture):
    """Tests that release() cleans up resources correctly."""
    camera = Camera()
    # Let the thread run
    time.sleep(0.1)

    # Access the thread object before it's gone
    thread = camera._thread
    assert thread.is_alive()

    camera.release()

    # The mock's release method should have been called
    mock_video_capture.release.assert_called_once()
    # The thread should be stopped
    assert not thread.is_alive()


def test_create_source_for_camera(mock_video_capture, test_settings):
    """Tests that the factory function can create a Camera source."""
    source = create_source("camera", settings_obj=test_settings)
    assert isinstance(source, Camera)
    source.release()
