import time
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from zebtrack.io.camera import Camera


class MockVideoCapture:
    """A more robust mock of cv2.VideoCapture for testing."""

    def __init__(self, *args, **kwargs):
        self._is_opened = True
        self._fail_read = False
        self._fail_open_attempts = 0
        self._open_calls = 0
        self.width = 1280
        self.height = 720
        self.fps = 30.0

    def isOpened(self):
        if self._open_calls > self._fail_open_attempts:
            self._is_opened = True
        return self._is_opened

    def read(self):
        if not self._is_opened or self._fail_read:
            return False, None
        return True, np.zeros((self.height, self.width, 3), np.uint8)

    def open(self, index):
        self._open_calls += 1
        if self._open_calls > self._fail_open_attempts:
            self._is_opened = True

    def release(self):
        self._is_opened = False

    def get(self, prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        if prop_id == cv2.CAP_PROP_FPS:
            return self.fps
        return 0

    def set(self, prop_id, value):
        pass

    def fail_read(self, fail=True):
        self._fail_read = fail

    def fail_open(self, attempts=0):
        self._is_opened = False
        self._fail_open_attempts = attempts
        self._open_calls = 0


@pytest.fixture
def mock_camera():
    """Fixture to provide a Camera instance with a mocked VideoCapture."""
    with patch("cv2.VideoCapture") as mock_cv2_vc:
        mock_vc_instance = MockVideoCapture()
        mock_cv2_vc.return_value = mock_vc_instance
        camera = Camera()
        yield camera, mock_vc_instance
        camera.release()


def test_camera_initialization(mock_camera):
    camera, _ = mock_camera
    assert camera._thread.is_alive()
    assert camera.get_properties()["width"] == 1280


def test_camera_reconnects_successfully(mock_camera):
    camera, mock_vc = mock_camera
    mock_vc.fail_open(attempts=2)  # Fail to open twice
    mock_vc.fail_read()  # Trigger disconnect

    time.sleep(6)  # 2 attempts * 2s sleep + buffer

    assert camera._thread.is_alive()
    ret, frame = camera.get_frame()
    assert ret
    assert frame is not None


def test_camera_gives_up_after_max_attempts(mock_camera):
    camera, mock_vc = mock_camera
    camera._max_reconnect_attempts = 2
    camera._reconnect_timeout_seconds = 10

    mock_vc.fail_open(attempts=3)  # Fail more than max_reconnect_attempts
    mock_vc.fail_read()

    time.sleep(6)  # 2 attempts * 2s sleep + buffer

    assert not camera._thread.is_alive()
    ret, frame = camera.get_frame()
    assert not ret


def test_camera_gives_up_after_timeout(mock_camera):
    camera, mock_vc = mock_camera
    camera._max_reconnect_attempts = 10
    camera._reconnect_timeout_seconds = 2

    mock_vc.fail_open(attempts=5)
    mock_vc.fail_read()

    time.sleep(4)

    assert not camera._thread.is_alive()
