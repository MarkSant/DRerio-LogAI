"""Extended unit tests for utils/video_frame_extractor.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.utils.video_frame_extractor import VideoFrameExtractor


class TestVideoFrameExtractorExtended:
    """Test VideoFrameExtractor frame reading, cropping, clamping, and saving."""

    @patch("cv2.VideoCapture")
    def test_extract_frame_success_first_frame(self, mock_cap_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        frame = VideoFrameExtractor.extract_frame("/path/video.mp4", 0)
        assert frame is not None
        assert frame.shape == (100, 100, 3)
        mock_cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_extract_frame_non_zero_index(self, mock_cap_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        fake_frame = np.ones((50, 50, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        frame = VideoFrameExtractor.extract_frame("/path/video.mp4", frame_index=15)
        assert frame is not None
        mock_cap.set.assert_called_once()
        mock_cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_extract_frame_open_failed(self, mock_cap_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap_cls.return_value = mock_cap

        frame = VideoFrameExtractor.extract_frame("/path/bad_video.mp4")
        assert frame is None
        mock_cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_extract_frame_read_failed(self, mock_cap_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cap_cls.return_value = mock_cap

        frame = VideoFrameExtractor.extract_frame("/path/corrupted.mp4")
        assert frame is None
        mock_cap.release.assert_called_once()

    @patch.object(VideoFrameExtractor, "extract_frame")
    def test_extract_and_crop_frame_success(self, mock_extract):
        mock_extract.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        cropped = VideoFrameExtractor.extract_and_crop_frame("/path/v.mp4", (10, 20, 50, 40))
        assert cropped is not None
        assert cropped.shape == (40, 50, 3)

    @patch.object(VideoFrameExtractor, "extract_frame")
    def test_extract_and_crop_frame_none_frame(self, mock_extract):
        mock_extract.return_value = None
        cropped = VideoFrameExtractor.extract_and_crop_frame("/path/v.mp4", (10, 20, 50, 40))
        assert cropped is None

    @patch.object(VideoFrameExtractor, "extract_frame")
    def test_extract_and_crop_frame_clamped(self, mock_extract):
        # Frame is 100x100, crop extends beyond boundaries
        mock_extract.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        cropped = VideoFrameExtractor.extract_and_crop_frame("/path/v.mp4", (80, 80, 50, 50))
        assert cropped is not None
        assert cropped.shape == (20, 20, 3)

    @patch.object(VideoFrameExtractor, "extract_frame")
    def test_extract_and_crop_frame_invalid_crop(self, mock_extract):
        # Frame is 100x100, crop width is 0 or negative
        mock_extract.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        cropped = VideoFrameExtractor.extract_and_crop_frame("/path/v.mp4", (10, 10, 0, 10))
        assert cropped is None

        cropped_neg = VideoFrameExtractor.extract_and_crop_frame("/path/v.mp4", (10, 10, 10, -5))
        assert cropped_neg is None

    @patch("cv2.imwrite", return_value=True)
    def test_save_frame_success(self, mock_imwrite):
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        success = VideoFrameExtractor.save_frame(frame, "/tmp/saved.png")
        assert success is True
        mock_imwrite.assert_called_once_with("/tmp/saved.png", frame)

    @patch("cv2.imwrite", return_value=False)
    def test_save_frame_failure(self, mock_imwrite):
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        success = VideoFrameExtractor.save_frame(frame, "/tmp/failed.png")
        assert success is False
