"""
Tests for zebtrack.io.video_source module.

Covers VideoFileSource: initialization, frame reading, metadata, error handling.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from zebtrack.io.video_source import VideoFileSource


class TestVideoFileSource(unittest.TestCase):
    """Test suite for VideoFileSource class."""

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_init_valid_video_from_path_object(self, mock_exists, mock_capture):
        """Test successful initialization with Path object for valid video."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [1920, 1080, 30.0, 600]  # width, height, fps, frame_count
        mock_capture.return_value = mock_cap

        video_path = Path("test_video.mp4")
        source = VideoFileSource(video_path)

        self.assertEqual(source.width, 1920)
        self.assertEqual(source.height, 1080)
        self.assertEqual(source.fps, 30.0)
        self.assertEqual(source.frame_count, 600)
        mock_capture.assert_called_once_with(str(video_path))

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_init_valid_video_from_string(self, mock_exists, mock_capture):
        """Test successful initialization with string path."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 25.0, 300]
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test_video.avi")

        self.assertEqual(source.width, 640)
        self.assertEqual(source.height, 480)
        self.assertEqual(source.fps, 25.0)
        self.assertEqual(source.frame_count, 300)

    @patch("zebtrack.io.video_source.Path.exists")
    def test_init_raises_file_not_found(self, mock_exists):
        """Test that FileNotFoundError is raised for non-existent file."""
        mock_exists.return_value = False

        with self.assertRaises(FileNotFoundError) as ctx:
            VideoFileSource("nonexistent_video.mp4")

        self.assertIn("Video file not found", str(ctx.exception))

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_init_raises_oserror_when_video_cannot_open(self, mock_exists, mock_capture):
        """Test that OSError is raised when cv2.VideoCapture cannot open the file."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_capture.return_value = mock_cap

        with self.assertRaises(OSError) as ctx:
            VideoFileSource("corrupted_video.mp4")

        self.assertIn("Cannot open video file", str(ctx.exception))

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_init_handles_zero_fps_with_warning(self, mock_exists, mock_capture):
        """Test that zero FPS is detected and defaults to 30, logging a warning."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # Return 0 for FPS (third call to get())
        mock_cap.get.side_effect = [1280, 720, 0.0, 500]
        mock_capture.return_value = mock_cap

        with patch("zebtrack.io.video_source.log") as mock_log:
            source = VideoFileSource("zero_fps_video.mp4")

            self.assertEqual(source.fps, 30)
            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args
            self.assertEqual(call_args[0][0], "video.fps.zero")

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_get_frame_success(self, mock_exists, mock_capture):
        """Test successful frame reading."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 100]

        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")
        ret, frame = source.get_frame()

        self.assertTrue(ret)
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.shape, (480, 640, 3))

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_get_frame_end_of_video(self, mock_exists, mock_capture):
        """Test get_frame returns False, None at end of video."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 10]
        mock_cap.read.return_value = (False, None)
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")
        ret, frame = source.get_frame()

        self.assertFalse(ret)
        self.assertIsNone(frame)

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_get_current_frame_number(self, mock_exists, mock_capture):
        """Test get_current_frame_number returns correct position."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [
            640,
            480,
            30.0,
            100,  # init calls
            42.0,  # CAP_PROP_POS_FRAMES
        ]
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")
        frame_number = source.get_current_frame_number()

        self.assertEqual(frame_number, 42.0)
        # Verify CAP_PROP_POS_FRAMES was requested
        mock_cap.get.assert_called_with(cv2.CAP_PROP_POS_FRAMES)

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_get_properties(self, mock_exists, mock_capture):
        """Test get_properties returns correct metadata dictionary."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [1280, 720, 60.0, 1800]
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")
        props = source.get_properties()

        expected = {
            "width": 1280,
            "height": 720,
            "fps": 60.0,
            "frame_count": 1800,
        }
        self.assertEqual(props, expected)

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_release_when_opened(self, mock_exists, mock_capture):
        """Test release() closes the video capture when opened."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 100]
        mock_capture.return_value = mock_cap

        with patch("zebtrack.io.video_source.log") as mock_log:
            source = VideoFileSource("test.mp4")
            source.release()

            mock_cap.release.assert_called_once()
            mock_log.info.assert_any_call("video.source.released", path=str(Path("test.mp4")))

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_release_when_not_opened(self, mock_exists, mock_capture):
        """Test release() does not call cap.release() if capture is not opened."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        # isOpened returns True during init (4 calls for get), then False at release time
        mock_cap.isOpened.side_effect = [True, False]
        mock_cap.get.side_effect = [640, 480, 30.0, 100]
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")
        source.release()

        # Should not call release on the cap since isOpened returns False at release time
        mock_cap.release.assert_not_called()

    @patch("zebtrack.io.video_source.cv2.VideoCapture")
    @patch("zebtrack.io.video_source.Path.exists")
    def test_multiple_frame_reads(self, mock_exists, mock_capture):
        """Test reading multiple frames in sequence."""
        mock_exists.return_value = True
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 3]

        frame1 = np.ones((480, 640, 3), dtype=np.uint8) * 50
        frame2 = np.ones((480, 640, 3), dtype=np.uint8) * 100
        frame3 = np.ones((480, 640, 3), dtype=np.uint8) * 150

        mock_cap.read.side_effect = [
            (True, frame1),
            (True, frame2),
            (True, frame3),
            (False, None),
        ]
        mock_capture.return_value = mock_cap

        source = VideoFileSource("test.mp4")

        ret1, f1 = source.get_frame()
        self.assertTrue(ret1)
        assert f1 is not None
        self.assertTrue(np.array_equal(f1, frame1))

        ret2, f2 = source.get_frame()
        self.assertTrue(ret2)
        assert f2 is not None
        self.assertTrue(np.array_equal(f2, frame2))

        ret3, f3 = source.get_frame()
        self.assertTrue(ret3)
        assert f3 is not None
        self.assertTrue(np.array_equal(f3, frame3))

        ret4, f4 = source.get_frame()
        self.assertFalse(ret4)
        self.assertIsNone(f4)


if __name__ == "__main__":
    unittest.main()
