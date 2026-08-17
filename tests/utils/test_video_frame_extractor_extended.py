"""Extended unit tests for utils/video_frame_extractor.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.utils.video_frame_extractor import VideoFrameExtractor


class TestVideoFrameExtractorExtended:
    """Test VideoFrameExtractor extraction, cropping, and saving."""

    def test_extract_frame_open_failed(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cap_cls.return_value = mock_cap

            frame = VideoFrameExtractor.extract_frame("nonexistent.mp4")
            assert frame is None
            mock_cap.release.assert_called_once()

    def test_extract_frame_read_failed(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (False, None)
            mock_cap_cls.return_value = mock_cap

            frame = VideoFrameExtractor.extract_frame("corrupt.mp4", frame_index=10)
            assert frame is None
            mock_cap.set.assert_called_once()
            mock_cap.release.assert_called_once()

    def test_extract_frame_success(self):
        mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, mock_img)
            mock_cap_cls.return_value = mock_cap

            frame = VideoFrameExtractor.extract_frame("video.mp4")
            assert frame is not None
            assert frame.shape == (100, 100, 3)

    def test_extract_and_crop_frame_none_frame(self):
        with patch.object(VideoFrameExtractor, "extract_frame", return_value=None):
            res = VideoFrameExtractor.extract_and_crop_frame("video.mp4", (0, 0, 50, 50))
            assert res is None

    def test_extract_and_crop_frame_invalid_crop_box(self):
        mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch.object(VideoFrameExtractor, "extract_frame", return_value=mock_img):
            # Crop box with negative or zero width/height results in None
            res = VideoFrameExtractor.extract_and_crop_frame("video.mp4", (0, 0, -10, 0))
            assert res is None

    def test_extract_and_crop_frame_valid(self):
        mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch.object(VideoFrameExtractor, "extract_frame", return_value=mock_img):
            cropped = VideoFrameExtractor.extract_and_crop_frame("video.mp4", (10, 10, 40, 40))
            assert cropped is not None
            assert cropped.shape == (40, 40, 3)

    def test_save_frame_success_and_failure(self):
        mock_img = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch("cv2.imwrite", return_value=True):
            assert VideoFrameExtractor.save_frame(mock_img, "out.png") is True

        with patch("cv2.imwrite", return_value=False):
            assert VideoFrameExtractor.save_frame(mock_img, "out.png") is False

        with patch("cv2.imwrite", side_effect=OSError("Disk full")):
            assert VideoFrameExtractor.save_frame(mock_img, "out.png") is False
