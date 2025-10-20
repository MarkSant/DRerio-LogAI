import itertools
import threading
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest


@pytest.fixture
def camera_and_mock():
    """
    Provides a Camera instance with a mocked VideoCapture and patched time.sleep
    to make tests fast and deterministic.
    """
    with (
        patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc,
        patch("zebtrack.io.camera.time.sleep"),
    ):  # No need to capture mock_sleep
        from zebtrack.io.camera import Camera

        mock_vc = MagicMock()
        mock_vc.isOpened.return_value = True
        # Initial dimensions returned during Camera.__init__
        mock_vc.get.side_effect = [1280, 720, 30.0]
        # Use itertools.repeat for infinite frame generation
        mock_vc.read.side_effect = itertools.repeat((True, np.zeros((720, 1280, 3), np.uint8)))
        mock_cv2_vc.return_value = mock_vc

        camera = Camera()
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


def test_camera_reconnects_successfully_and_updates_dimensions(camera_and_mock, monkeypatch):
    """Test that the camera can recover and updates its properties."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 5)

    is_opened_sequence = [True, False, False, True]
    read_sequence = [(False, None), (True, np.zeros((1, 1, 3)))]
    # This side_effect will be applied *after* the initial gets in the fixture.
    # It provides the NEW dimensions after the reconnect.
    get_sequence = [640, 480, 60.0]

    mock_vc.isOpened.side_effect = itertools.chain(is_opened_sequence, itertools.repeat(True))
    mock_vc.read.side_effect = itertools.chain(
        read_sequence, itertools.repeat((True, np.zeros((1, 1, 3))))
    )
    mock_vc.get.side_effect = itertools.chain(get_sequence, itertools.repeat(60.0))

    camera._thread.join(timeout=2.0)

    assert camera._thread.is_alive()
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

    mock_vc.isOpened.return_value = False
    mock_vc.read.side_effect = itertools.repeat((False, None))

    camera._thread.join(timeout=2.0)

    assert not camera._thread.is_alive()
    assert mock_vc.open.call_count == 2


def test_camera_gives_up_after_timeout(camera_and_mock, monkeypatch):
    """Test that the camera thread stops after the global timeout is exceeded."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 99)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0.1)

    mock_vc.isOpened.return_value = False
    mock_vc.read.side_effect = itertools.repeat((False, None))
    with patch("zebtrack.io.camera.time.time") as mock_time:
        # Provide initial time values and then keep returning time after timeout
        mock_time.side_effect = itertools.chain([100.0, 100.0, 100.2], itertools.repeat(100.2))
        camera._thread.join(timeout=2.0)

    assert not camera._thread.is_alive()
    assert mock_vc.open.call_count >= 1


def test_camera_reconnects_indefinitely_when_limits_are_zero(camera_and_mock, monkeypatch):
    """Test that the camera keeps trying to reconnect if max_attempts and timeout are 0."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 0)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0)

    mock_vc.isOpened.return_value = False
    mock_vc.read.side_effect = itertools.repeat((False, None))

    camera._thread.join(timeout=0.2)  # Short join to let it run a bit
    assert camera._thread.is_alive()
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
