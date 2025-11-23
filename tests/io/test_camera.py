import itertools
import threading
import time
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest


@pytest.fixture
def camera_and_mock():
    """
    Provides a Camera instance with a mocked VideoCapture.
    Uses real time but mocked CV2.
    """
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc:
        from zebtrack.io.camera import Camera

        # Create mock settings
        mock_settings = MagicMock()
        mock_settings.camera.index = 0
        mock_settings.camera.desired_width = 1280
        mock_settings.camera.desired_height = 720
        mock_settings.camera.max_reconnect_attempts = 10
        mock_settings.camera.reconnect_timeout_seconds = 30.0
        mock_settings.video_processing.fps = 30.0

        mock_vc = MagicMock()
        mock_vc.isOpened.return_value = True
        # Initial dimensions returned during Camera.__init__
        mock_vc.get.side_effect = [1280, 720, 30.0]
        # Use itertools.repeat for infinite frame generation
        mock_vc.read.side_effect = itertools.repeat((True, np.zeros((720, 1280, 3), np.uint8)))
        mock_cv2_vc.return_value = mock_vc

        camera = Camera(settings_obj=mock_settings)
        yield camera, mock_vc
        camera.release()


def test_camera_initialization(camera_and_mock):
    """Verify that the camera initializes correctly and the thread starts."""
    camera, mock_vc = camera_and_mock
    assert camera._thread.is_alive()
    props = camera.get_properties()
    assert props["width"] == 1280
    assert props["fps"] == 30.0
    mock_vc.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 1280)


def test_camera_is_opened(camera_and_mock):
    """Test that is_opened() returns the correct status."""
    camera, mock_vc = camera_and_mock

    # Initially opened
    mock_vc.isOpened.return_value = True
    assert camera.is_opened() is True

    # Simulate camera closing
    mock_vc.isOpened.return_value = False
    assert camera.is_opened() is False


def test_camera_reconnects_successfully_and_updates_dimensions(camera_and_mock, monkeypatch):
    """Test that the camera can recover and updates its properties."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 5)
    monkeypatch.setattr(camera, "_reconnect_retry_delay", 0.01)

    is_opened_sequence = [True, False, False, True]
    read_sequence = [(False, None), (True, np.zeros((1, 1, 3)))]
    # This side_effect will be applied *after* the initial gets in the fixture.
    get_sequence = [640, 480, 60.0]

    mock_vc.isOpened.side_effect = itertools.chain(is_opened_sequence, itertools.repeat(True))
    mock_vc.read.side_effect = itertools.chain(
        read_sequence, itertools.repeat((True, np.zeros((1, 1, 3))))
    )
    mock_vc.get.side_effect = itertools.chain(get_sequence, itertools.repeat(60.0))

    # Wait enough time for reconnect logic (real time now)
    # Defaults: sleep(0.1) in capture failure. retry_delay 0.05.
    # Sequence: True -> read (False) -> sleep 0.1 -> False (isOpened) -> reconnect.
    # Reconnect (attempt 1): wait 0.05.
    # Reconnect (attempt 2): wait 0.05.
    # True (isOpened).
    time.sleep(1.0)

    assert camera._thread.is_alive()
    # Open called 2 times (attempt 1, attempt 2)
    assert mock_vc.open.call_count == 2
    assert camera._reconnect_attempts == 0
    # Verify that the camera properties were updated
    props = camera.get_properties()
    assert props["width"] == 640
    assert props["height"] == 480
    assert props["fps"] == 60.0


def test_camera_gives_up_after_max_attempts(camera_and_mock, monkeypatch):
    """Test that the camera thread stops after exceeding max reconnect attempts."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 2)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 10)

    # Ensure retry delay is small to speed up test
    monkeypatch.setattr(camera, "_reconnect_retry_delay", 0.01)

    mock_vc.isOpened.side_effect = itertools.repeat(False)
    mock_vc.read.side_effect = itertools.repeat((False, None))

    # Should try 2 times then abort. 2 * 0.01s = 0.02s.
    # Give it plenty of time.
    camera._thread.join(timeout=2.0)

    assert not camera._thread.is_alive()
    assert mock_vc.open.call_count == 2


def test_camera_gives_up_after_timeout(camera_and_mock, monkeypatch):
    """Test that the camera thread stops after the global timeout is exceeded."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 99)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0.1)
    monkeypatch.setattr(camera, "_reconnect_retry_delay", 0.01)

    mock_vc.isOpened.side_effect = itertools.repeat(False)
    mock_vc.read.side_effect = itertools.repeat((False, None))

    # Timeout is 0.1s. Retry is 0.01s. Should try ~10 times.
    # Wait 0.5s.
    camera._thread.join(timeout=1.0)

    assert not camera._thread.is_alive()
    # Should have called open multiple times
    assert mock_vc.open.call_count >= 2


def test_camera_reconnects_indefinitely_when_limits_are_zero(camera_and_mock, monkeypatch):
    """Test that the camera keeps trying to reconnect if max_attempts and timeout are 0."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 0)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0)
    monkeypatch.setattr(camera, "_reconnect_retry_delay", 0.01)

    mock_vc.isOpened.side_effect = itertools.repeat(False)
    mock_vc.read.side_effect = itertools.repeat((False, None))

    time.sleep(0.2)
    assert camera._thread.is_alive()
    # 0.2s / 0.01s = ~20 calls. Should be > 2.
    assert mock_vc.open.call_count > 2


def test_get_properties_is_thread_safe(camera_and_mock, monkeypatch):
    """Verify that get_properties() does not return inconsistent data during reconnect."""
    camera, mock_vc = camera_and_mock

    # Events to synchronize the main test, the reader thread, and the getter threads
    reconnect_started = threading.Event()
    getters_can_start = threading.Event()
    test_finished = threading.Event()
    inconsistent_states = []

    # New dimensions that will be set during the reconnect
    new_dimensions = [640, 480, 60.0]

    def controlled_open(*args, **kwargs):
        """This mock for cap.open() controls the test synchronization."""
        reconnect_started.set()  # Signal that the reader thread is in the reconnect logic
        getters_can_start.wait(timeout=1)  # Wait for the getter threads to start
        # Now allow the reconnect to complete
        return True

    mock_vc.open.side_effect = controlled_open
    mock_vc.isOpened.side_effect = itertools.chain(
        [True, False, True, True, True], itertools.repeat(True)
    )
    mock_vc.read.side_effect = itertools.chain(
        [(False, None), (True, np.zeros((1, 1, 3)))], itertools.repeat((True, np.zeros((1, 1, 3))))
    )
    mock_vc.get.side_effect = itertools.chain(new_dimensions, itertools.repeat(60.0))

    def property_getter():
        """This function will be run by multiple threads to hammer get_properties()."""
        while not test_finished.is_set():
            props = camera.get_properties()
            # Check for an inconsistent state (new width with old height or vice-versa)
            is_consistent = (props["width"] == 1280 and props["height"] == 720) or (
                props["width"] == 640 and props["height"] == 480
            )
            if not is_consistent:
                inconsistent_states.append(props)

    # Start multiple getter threads
    getter_threads = [threading.Thread(target=property_getter) for _ in range(5)]
    for t in getter_threads:
        t.start()

    # Wait for the reader thread to enter the reconnect logic
    reconnect_started.wait(timeout=2)
    # Allow the getter threads to start hammering the get_properties method
    getters_can_start.set()

    # Wait for the reader thread to complete the reconnect and run for a bit
    camera._thread.join(timeout=2.0)

    # Signal the getter threads to stop
    test_finished.set()
    for t in getter_threads:
        t.join(timeout=1)

    # The test passes if no inconsistent states were ever recorded
    assert not inconsistent_states, f"Found inconsistent states: {inconsistent_states}"
