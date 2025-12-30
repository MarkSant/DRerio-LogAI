"""Regression tests for configurable aquarium detection thresholds."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.aquarium_detector import AquariumDetector


@pytest.fixture
def mock_frame():
    """Create a 100x100 frame."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def mock_yolo_result_15_percent():
    """Create a mock YOLO result with a mask of 1500 pixels (15% of 100x100)."""
    mock_box = MagicMock()
    mock_box.conf = 0.95
    mock_box.cls = 0

    # 15x100 = 1500 pixels = 15% area
    polygon = np.array([[0, 0], [15, 0], [15, 100], [0, 100]], dtype=np.int32)

    mock_masks = MagicMock()
    mock_masks.xy = [polygon]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.masks = mock_masks

    return [mock_result]


@pytest.fixture
def mock_yolo_result_5_percent():
    """Create a mock YOLO result with 5% area."""
    mock_box = MagicMock()
    mock_box.conf = 0.95

    # 5x100 = 500 pixels = 5% area
    polygon = np.array([[0, 0], [5, 0], [5, 100], [0, 100]], dtype=np.int32)

    mock_masks = MagicMock()
    mock_masks.xy = [polygon]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.masks = mock_masks
    return [mock_result]


@patch("zebtrack.core.aquarium_detector.YOLO")
def test_detect_aquariums_default_thresholds(mock_yolo, mock_frame, mock_yolo_result_15_percent):
    """Test that default threshold (0.1) accepts 15% area."""
    mock_model = MagicMock()
    mock_model.predict.return_value = mock_yolo_result_15_percent
    mock_yolo.return_value = mock_model

    detector = AquariumDetector("mock_model.pt", mode="seg")

    # Run detection on "video"
    with patch("zebtrack.core.aquarium_detector.VideoFileSource") as MockVideoSource:
        instance = MockVideoSource.return_value
        instance.get_frame.return_value = (True, mock_frame)

        # Should succeed with default (0.1)
        polygons = detector.detect_aquariums("mock_video.mp4", stabilization_frames=1)

        assert len(polygons) == 1
        assert len(polygons[0]) == 4


@patch("zebtrack.core.aquarium_detector.YOLO")
def test_detect_aquariums_strict_threshold(mock_yolo, mock_frame, mock_yolo_result_15_percent):
    """Test that stricter threshold (0.2) rejects 15% area."""
    mock_model = MagicMock()
    mock_model.predict.return_value = mock_yolo_result_15_percent
    mock_yolo.return_value = mock_model

    detector = AquariumDetector("mock_model.pt", mode="seg")

    with patch("zebtrack.core.aquarium_detector.VideoFileSource") as MockVideoSource:
        instance = MockVideoSource.return_value
        instance.get_frame.return_value = (True, mock_frame)

        # Set stricter min_area_ratio = 0.2
        polygons = detector.detect_aquariums(
            "mock_video.mp4", stabilization_frames=1, min_area_ratio=0.2
        )

        # Should fail (return empty or default, depending on fallback, but here we expect handled empty list from filtering, then consensus fail or default)
        # Note: consensus generates default if list empty. But good_polygons will be empty.

        # Wait, if good_polygons is empty, it returns default polygon (80% frame).
        # We need to check that the returned polygon is NOT our 15% polygon.

        # The 15% polygon has width 15. The default one has margin 10% -> 10,10 to 90,90 -> width 80.

        # However, _find_consensus_polygon returns default only if `good_polygons` is empty.
        # So we assert that result is NOT the input polygon.

        if polygons:
            poly = polygons[0]
            # Check width
            width = poly[:, 0].max() - poly[:, 0].min()
            assert width != 15  # Should not be the 15% polygon


@patch("zebtrack.core.aquarium_detector.YOLO")
def test_process_segmentation_logic_direct(mock_yolo, mock_frame, mock_yolo_result_15_percent):
    """Test standard logic directly."""
    detector = AquariumDetector("mock_model.pt", mode="seg")

    # 1. 15% Area, min=0.1 -> Accept
    result = detector._process_segmentation_results(
        mock_frame, mock_yolo_result_15_percent, 0, min_area_ratio=0.1
    )
    assert result is not None

    # 2. 15% Area, min=0.2 -> Reject
    result = detector._process_segmentation_results(
        mock_frame, mock_yolo_result_15_percent, 0, min_area_ratio=0.2
    )
    assert result is None
