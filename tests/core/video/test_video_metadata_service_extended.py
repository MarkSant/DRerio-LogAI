"""
Extended unit tests for VideoMetadataService in core/video/video_metadata_service.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import cv2
import pytest

from zebtrack.core.video.video_metadata_service import VideoMetadataService


class TestVideoMetadataServiceExtended:
    """Test VideoMetadataService extraction of dimensions and info."""

    def test_get_video_dimensions_success(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 1920.0,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080.0,
        }.get(prop, 0.0)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            dims = VideoMetadataService.get_video_dimensions("/path/to/video.mp4")
            assert dims == (1920, 1080)
            mock_cap.release.assert_called_once()

    def test_get_video_dimensions_cannot_open_raises(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError, match="Could not open video"):
                VideoMetadataService.get_video_dimensions("/bad/video.mp4")

    def test_get_video_dimensions_zero_dimensions_raises(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 0.0

        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError, match="Invalid dimensions"):
                VideoMetadataService.get_video_dimensions("/zero/video.mp4")

    def test_get_video_info_success(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
            cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_COUNT: 900.0,
        }.get(prop, 0.0)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            info = VideoMetadataService.get_video_info("/path/to/video.mp4")
            assert info["width"] == 1280
            assert info["height"] == 720
            assert info["fps"] == 30.0
            assert info["frame_count"] == 900
            mock_cap.release.assert_called_once()

    def test_get_video_info_cannot_open_raises(self):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError, match="Could not open video"):
                VideoMetadataService.get_video_info("/bad/video.mp4")
