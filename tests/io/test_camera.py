import itertools
import time
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
    with patch("zebtrack.io.camera.cv2.VideoCapture") as mock_cv2_vc, \
         patch("zebtrack.io.camera.time.sleep"):  # No need to capture mock_sleep
        from zebtrack.io.camera import Camera

        mock_vc = MagicMock()
        mock_vc.isOpened.return_value = True
        # Initial dimensions returned during Camera.__init__
        mock_vc.get.side_effect = [1280, 720, 30.0]
        mock_vc.read.return_value = (True, np.zeros((720, 1280, 3), np.uint8))
        mock_cv2_vc.return_value = mock_vc

        camera = Camera()
        yield camera, mock_vc
        camera.release()


def test_camera_initialization(camera_and_mock):
    """Verify that the camera initializes correctly and the thread starts."""
    camera, mock_vc = camera_and_mock
    assert camera._thread.is_alive()
    assert camera.get_properties()["width"] == 1280
    mock_vc.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 1280)


def test_camera_reconnects_successfully_and_updates_dimensions(camera_and_mock, monkeypatch):
    """Test that the camera can recover and updates its properties."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 5)

    is_opened_sequence = [True, False, False, True]
    read_sequence = [(False, None), (True, np.zeros((1, 1, 3)))]
    # This side_effect will be applied *after* the initial gets in the fixture.
    # It provides the NEW dimensions after the reconnect.
    get_sequence = [640, 480, 30.0]

    mock_vc.isOpened.side_effect = itertools.chain(is_opened_sequence, itertools.repeat(True))
    mock_vc.read.side_effect = itertools.chain(read_sequence, itertools.repeat((True, np.zeros((1, 1, 3)))))
    mock_vc.get.side_effect = itertools.chain(get_sequence, itertools.repeat(30.0))

    camera._thread.join(timeout=0.5)

    assert camera._thread.is_alive()
    assert mock_vc.open.call_count == 2
    assert camera._reconnect_attempts == 0
    # Verify that the camera properties were updated
    assert camera.actual_width == 640
    assert camera.actual_height == 480


def test_camera_gives_up_after_max_attempts(camera_and_mock, monkeypatch):
    """Test that the camera thread stops after exceeding max reconnect attempts."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 2)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 10)

    mock_vc.isOpened.return_value = False
    mock_vc.read.return_value = (False, None)

    camera._thread.join(timeout=0.5)

    assert not camera._thread.is_alive()
    assert mock_vc.open.call_count == 2


def test_camera_gives_up_after_timeout(camera_and_mock, monkeypatch):
    """Test that the camera thread stops after the global timeout is exceeded."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 99)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0.1)

    mock_vc.isOpened.return_value = False
    with patch("zebtrack.io.camera.time.time") as mock_time:
        mock_time.side_effect = [100.0, 100.0, 100.2]
        camera._thread.join(timeout=0.5)

    assert not camera._thread.is_alive()
    assert mock_vc.open.call_count >= 1

def test_camera_reconnects_indefinitely_when_limits_are_zero(camera_and_mock, monkeypatch):
    """Test that the camera keeps trying to reconnect if max_attempts and timeout are 0."""
    camera, mock_vc = camera_and_mock
    monkeypatch.setattr(camera, "_max_reconnect_attempts", 0)
    monkeypatch.setattr(camera, "_reconnect_timeout_seconds", 0)

    mock_vc.isOpened.return_value = False

    camera._thread.join(timeout=0.1)
    assert camera._thread.is_alive()
    assert mock_vc.open.call_count > 2
