"""Tests for VideoMetadataService."""

from unittest.mock import Mock, patch

import cv2
import pytest

from zebtrack.core.video.video_metadata_service import VideoMetadataService


@patch("zebtrack.core.video.video_metadata_service.cv2.VideoCapture")
def test_get_video_dimensions_success(mock_video_capture):
    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: 1920,
        cv2.CAP_PROP_FRAME_HEIGHT: 1080,
    }[prop]
    mock_video_capture.return_value = mock_cap

    result = VideoMetadataService.get_video_dimensions("/path/to/video.mp4")

    assert result == (1920, 1080)
    mock_cap.release.assert_called_once()


@patch("zebtrack.core.video.video_metadata_service.cv2.VideoCapture")
def test_get_video_dimensions_open_fail(mock_video_capture):
    mock_cap = Mock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    with pytest.raises(ValueError, match="Could not open video"):
        VideoMetadataService.get_video_dimensions("/path/to/video.mp4")


@patch("zebtrack.core.video.video_metadata_service.cv2.VideoCapture")
def test_get_video_dimensions_invalid_values(mock_video_capture):
    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: 0,
        cv2.CAP_PROP_FRAME_HEIGHT: 0,
    }[prop]
    mock_video_capture.return_value = mock_cap

    with pytest.raises(ValueError, match="Invalid dimensions"):
        VideoMetadataService.get_video_dimensions("/path/to/video.mp4")


@patch("zebtrack.core.video.video_metadata_service.cv2.VideoCapture")
def test_get_video_info_success(mock_video_capture):
    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: 640,
        cv2.CAP_PROP_FRAME_HEIGHT: 480,
        cv2.CAP_PROP_FPS: 25.0,
        cv2.CAP_PROP_FRAME_COUNT: 1000,
    }[prop]
    mock_video_capture.return_value = mock_cap

    info = VideoMetadataService.get_video_info("/path/to/video.mp4")

    assert info == {"width": 640, "height": 480, "fps": 25.0, "frame_count": 1000}
    mock_cap.release.assert_called_once()


@patch("zebtrack.core.video.video_metadata_service.cv2.VideoCapture")
def test_get_video_info_open_fail(mock_video_capture):
    mock_cap = Mock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    with pytest.raises(ValueError, match="Could not open video"):
        VideoMetadataService.get_video_info("/path/to/video.mp4")
