"""
Extended unit tests for video helper functions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from zebtrack.utils.video import get_video_dimensions


class TestVideoExtended:
    def test_get_video_dimensions_success(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = lambda prop: 1920.0 if prop == 3 else 1080.0
            mock_cap_cls.return_value = mock_cap

            dims = get_video_dimensions("/path/to/video.mp4")
            assert dims == (1920, 1080)
            mock_cap.release.assert_called_once()

    def test_get_video_dimensions_failed_to_open(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cap_cls.return_value = mock_cap

            dims = get_video_dimensions("/path/to/invalid.mp4")
            assert dims is None
            mock_cap.release.assert_called_once()

    def test_get_video_dimensions_invalid_dims(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.return_value = 0.0
            mock_cap_cls.return_value = mock_cap

            dims = get_video_dimensions("/path/to/empty.mp4")
            assert dims is None

    def test_get_video_dimensions_exception_handled(self):
        with patch("cv2.VideoCapture", side_effect=OSError("Read error")):
            dims = get_video_dimensions("/path/to/corrupt.mp4")
            assert dims is None


class TestVideoExtended2:
    def test_get_video_dimensions_cannot_open(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cap_cls.return_value = mock_cap

            assert get_video_dimensions("fake.mp4") is None
            mock_cap.release.assert_called_once()

    def test_get_video_dimensions_invalid_size(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = [0.0, 0.0]
            mock_cap_cls.return_value = mock_cap

            assert get_video_dimensions(Path("invalid.mp4")) is None

    def test_get_video_dimensions_success(self):
        with patch("cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = [1920.0, 1080.0]
            mock_cap_cls.return_value = mock_cap

            dim = get_video_dimensions("hd_video.mp4")
            assert dim == (1920, 1080)

    def test_get_video_dimensions_exception(self):
        with patch("cv2.VideoCapture", side_effect=OSError("File read error")):
            assert get_video_dimensions("error.mp4") is None
