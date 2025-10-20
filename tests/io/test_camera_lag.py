"""
Tests for camera frame buffer and lag detection.

This module tests the deque-based frame buffer implementation in Camera class,
ensuring that:
- Old frames are automatically discarded (only 2 most recent frames kept)
- Frame lag is correctly calculated and logged
- Warnings are emitted when lag exceeds threshold
"""

import itertools
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.io.camera import Camera


@pytest.fixture
def mock_cv2_capture():
    """Create a mock OpenCV VideoCapture object."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: {
        3: 1280,  # CAP_PROP_FRAME_WIDTH
        4: 720,  # CAP_PROP_FRAME_HEIGHT
        5: 30.0,  # CAP_PROP_FPS
    }.get(prop, 0)
    return mock_cap


@pytest.mark.unit
def test_frame_buffer_keeps_only_recent_frames(mock_cv2_capture):
    """Test that buffer only keeps 2 most recent frames."""
    # Create test frames
    frame1 = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame1[0, 0] = [1, 1, 1]  # Mark frame 1

    frame2 = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame2[0, 0] = [2, 2, 2]  # Mark frame 2

    frame3 = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame3[0, 0] = [3, 3, 3]  # Mark frame 3

    # Mock camera to return frames sequentially, then keep returning frame3
    mock_cv2_capture.read.side_effect = itertools.chain(
        [
            (True, frame1),
            (True, frame2),
            (True, frame3),
        ],
        itertools.repeat((True, frame3)),  # Keep returning frame3
    )

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        camera = Camera()

        # Wait for frames to be captured
        time.sleep(0.3)

        # Get frame - should be frame3 (most recent)
        ret, frame = camera.get_frame()

        assert ret is True
        assert frame is not None
        # Verify it's frame 3 (not frame 1 or 2)
        np.testing.assert_array_equal(frame[0, 0], [3, 3, 3])

        # Verify buffer size is limited to 2
        with camera._lock:
            assert len(camera._frame_buffer) <= 2
            assert len(camera._frame_timestamps) <= 2

        camera.release()


@pytest.mark.unit
def test_lag_warning_when_threshold_exceeded(mock_cv2_capture):
    """Test that warning is logged when frame lag exceeds threshold."""
    test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Mock camera to return one frame and then keep returning it
    mock_cv2_capture.read.side_effect = itertools.repeat((True, test_frame))

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        # Temporarily reduce lag threshold for faster test
        with patch("zebtrack.settings.settings.camera.max_frame_lag_ms", 100.0):
            # Mock the logger to capture warnings
            with patch("zebtrack.io.camera.log") as mock_log:
                camera = Camera()

                # Wait for frame to be captured
                time.sleep(0.1)

                # Manually set old timestamp to simulate lag
                with camera._lock:
                    if camera._frame_timestamps:
                        # Set timestamp to 200ms in the past (exceeds 100ms threshold)
                        camera._frame_timestamps[-1] = time.time() - 0.2

                # Get frame - should trigger warning
                ret, frame = camera.get_frame()

                assert ret is True
                assert frame is not None

                # Verify warning was logged
                mock_log.warning.assert_called_once()
                call_args = mock_log.warning.call_args
                assert call_args[0][0] == "camera.lag.threshold_exceeded"

                camera.release()


@pytest.mark.unit
def test_get_frame_returns_most_recent_frame(mock_cv2_capture):
    """Test that get_frame always returns the most recent frame."""
    # Create distinguishable frames
    frames = []
    for i in range(5):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[0, 0] = [i, i, i]  # Mark each frame uniquely
        frames.append((True, frame))

    # After 5 frames, keep returning the last frame
    last_frame = frames[-1][1]  # Get frame 4
    mock_cv2_capture.read.side_effect = itertools.chain(
        frames, itertools.repeat((True, last_frame))
    )

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        camera = Camera()

        # Wait for all frames to be captured
        time.sleep(0.5)

        # Get frame multiple times - should always be the most recent (frame 4)
        for _ in range(3):
            ret, frame = camera.get_frame()
            assert ret is True
            assert frame is not None
            # Should be frame 4 (last frame before stop signal)
            np.testing.assert_array_equal(frame[0, 0], [4, 4, 4])

        camera.release()


@pytest.mark.unit
def test_get_frame_returns_false_when_no_frames_available(mock_cv2_capture):
    """Test that get_frame returns (False, None) when no frames captured yet."""
    # Mock camera that fails immediately and keeps failing
    mock_cv2_capture.read.side_effect = itertools.repeat((False, None))

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        camera = Camera()

        # Immediately try to get frame before any successful read
        ret, frame = camera.get_frame()

        assert ret is False
        assert frame is None

        camera.release()


@pytest.mark.unit
def test_buffer_clears_on_read_failure(mock_cv2_capture):
    """Test that buffer is cleared when camera read fails."""
    test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Control the mock behavior with time-based switching
    start_time = [None]
    fail_after = [False]

    def mock_read():
        if start_time[0] is None:
            start_time[0] = time.time()

        # Succeed for first 0.3 seconds, then start failing
        elapsed = time.time() - start_time[0]
        if elapsed < 0.3:
            return (True, test_frame)
        else:
            fail_after[0] = True
            return (False, None)

    mock_cv2_capture.read.side_effect = mock_read

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        camera = Camera()

        # Wait for success frames to be captured
        time.sleep(0.2)

        # Verify frame is available
        ret, frame = camera.get_frame()
        assert ret is True
        assert frame is not None

        # Wait for failure to kick in and be processed
        time.sleep(0.4)

        # After failure, buffer should be cleared
        with camera._lock:
            assert len(camera._frame_buffer) == 0
            assert len(camera._frame_timestamps) == 0
            assert camera._frame_available is False

        # get_frame should return False
        ret, frame = camera.get_frame()
        assert ret is False
        assert frame is None

        camera.release()


@pytest.mark.unit
def test_frame_timestamps_match_buffer_length(mock_cv2_capture):
    """Test that timestamps deque always has same length as frame buffer."""
    frames = [(True, np.zeros((720, 1280, 3), dtype=np.uint8)) for _ in range(10)]

    mock_cv2_capture.read.side_effect = itertools.chain(frames, itertools.repeat((False, None)))

    with patch("zebtrack.io.camera.cv2.VideoCapture", return_value=mock_cv2_capture):
        camera = Camera()

        # Wait for frames to be captured
        time.sleep(0.5)

        # Verify buffer and timestamps have same length
        with camera._lock:
            assert len(camera._frame_buffer) == len(camera._frame_timestamps)
            # With maxlen=2, should not exceed 2 items
            assert len(camera._frame_buffer) <= 2
            assert len(camera._frame_timestamps) <= 2

        camera.release()
