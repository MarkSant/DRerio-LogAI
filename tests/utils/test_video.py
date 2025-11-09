"""
Unit tests for video utility functions.

Tests for get_video_dimensions and related utilities.
"""

import unittest
from unittest.mock import Mock, patch

import cv2

from zebtrack.utils.video import get_video_dimensions


class TestGetVideoDimensions(unittest.TestCase):
    """Test suite for get_video_dimensions function."""

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_successful_dimensions_retrieval(self, mock_video_capture):
        """Test successful video dimensions retrieval."""
        # Setup mock
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080,
        }[prop]
        mock_video_capture.return_value = mock_cap

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result == (1920, 1080)
        mock_cap.release.assert_called_once()

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_failed_to_open_video(self, mock_video_capture):
        """Test when video cannot be opened."""
        # Setup mock
        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_video_capture.return_value = mock_cap

        # Test
        result = get_video_dimensions("/path/to/nonexistent.mp4")

        # Verify
        assert result is None
        mock_cap.release.assert_called_once()

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_invalid_dimensions(self, mock_video_capture):
        """Test when video returns invalid dimensions."""
        # Setup mock
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 0,
            cv2.CAP_PROP_FRAME_HEIGHT: 0,
        }[prop]
        mock_video_capture.return_value = mock_cap

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result is None
        mock_cap.release.assert_called_once()

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_cv2_error_exception(self, mock_video_capture):
        """Test handling of cv2.error exception."""
        # Setup mock to raise cv2.error
        mock_video_capture.side_effect = cv2.error("Test error")

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result is None

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_oserror_exception(self, mock_video_capture):
        """Test handling of OSError exception."""
        # Setup mock to raise OSError
        mock_video_capture.side_effect = OSError("File not found")

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result is None

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_valueerror_exception(self, mock_video_capture):
        """Test handling of ValueError exception."""
        # Setup mock
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = ValueError("Invalid property")
        mock_video_capture.return_value = mock_cap

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result is None
        mock_cap.release.assert_called_once()

    @patch("zebtrack.utils.video.cv2.VideoCapture")
    def test_release_called_on_exception_after_open(self, mock_video_capture):
        """Test that release is called even when an exception occurs after opening."""
        # Setup mock that raises after isOpened
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = ValueError("Test error")
        mock_video_capture.return_value = mock_cap

        # Test
        result = get_video_dimensions("/path/to/video.mp4")

        # Verify
        assert result is None
        # Verify release was called in finally block
        mock_cap.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
