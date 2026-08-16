"""
Extended unit tests for VideoFrameExtractor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.utils.video_frame_extractor import VideoFrameExtractor


class TestVideoFrameExtractorExtended:
    """Test VideoFrameExtractor extraction and cropping."""

    def test_extract_frame_success(self):
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, dummy_frame)
            mock_cap_cls.return_value = mock_cap

            frame = VideoFrameExtractor.extract_frame("/path/to/video.mp4", frame_index=10)
            assert frame is dummy_frame
            mock_cap.set.assert_called_once()
            mock_cap.release.assert_called_once()

    def test_extract_frame_not_opened_or_read_failed(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cap_cls.return_value = mock_cap

            assert VideoFrameExtractor.extract_frame("/path/to/video.mp4") is None

        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (False, None)
            mock_cap_cls.return_value = mock_cap

            assert VideoFrameExtractor.extract_frame("/path/to/video.mp4") is None

    def test_extract_and_crop_frame(self):
        dummy_frame = np.ones((480, 640, 3), dtype=np.uint8) * 100
        with patch.object(VideoFrameExtractor, "extract_frame", return_value=dummy_frame):
            # Valid crop
            cropped = VideoFrameExtractor.extract_and_crop_frame(
                "/path/to/video.mp4",
                crop_box=(10, 10, 100, 100),
            )
            assert cropped is not None
            assert cropped.shape == (100, 100, 3)

            # Invalid crop resulting in empty region (zero width/height)
            invalid_cropped = VideoFrameExtractor.extract_and_crop_frame(
                "/path/to/video.mp4",
                crop_box=(10, 10, 0, 0),
            )
            assert invalid_cropped is None

            # Out of bounds crop adjusted to frame boundary
            adjusted_cropped = VideoFrameExtractor.extract_and_crop_frame(
                "/path/to/video.mp4",
                crop_box=(-10, -10, 800, 600),
            )
            assert adjusted_cropped is not None
            assert adjusted_cropped.shape == (480, 640, 3)

        with patch.object(VideoFrameExtractor, "extract_frame", return_value=None):
            res = VideoFrameExtractor.extract_and_crop_frame("/path/to/video.mp4", (0, 0, 10, 10))
            assert res is None

    def test_save_frame(self):
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch("cv2.imwrite", return_value=True) as mock_imwrite:
            assert VideoFrameExtractor.save_frame(dummy_frame, "/path/to/out.png") is True
            mock_imwrite.assert_called_once_with("/path/to/out.png", dummy_frame)

        with patch("cv2.imwrite", return_value=False):
            assert VideoFrameExtractor.save_frame(dummy_frame, "/path/to/out.png") is False

        with patch("cv2.imwrite", side_effect=OSError("Disk error")):
            assert VideoFrameExtractor.save_frame(dummy_frame, "/path/to/out.png") is False
