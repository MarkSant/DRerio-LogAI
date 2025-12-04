"""Comprehensive tests for plugins/ultralytics_detector.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin
from zebtrack.settings import Settings, load_settings


@pytest.fixture
def mock_yolo_model():
    """Create a mock YOLO model."""
    mock = MagicMock()
    mock.predict = MagicMock()
    return mock


@pytest.fixture
def mock_ultralytics_import():
    """Mock the ultralytics import."""
    with (
        patch("zebtrack.plugins.ultralytics_detector.ULTRALYTICS_AVAILABLE", True),
        patch("zebtrack.plugins.ultralytics_detector.YOLO") as mock_yolo_class,
    ):
        yield mock_yolo_class


@pytest.fixture
def settings_obj() -> Settings:
    """Load settings for tests."""
    return load_settings()


def test_ultralytics_detector_init_with_settings(mock_ultralytics_import, settings_obj):
    """Test initialization with settings object."""
    mock_model_instance = MagicMock()
    mock_model_instance.names = {0: "aqua", 1: "zebrafish"}  # Add class names
    mock_ultralytics_import.return_value = mock_model_instance

    detector = UltralyticsDetectorPlugin(model_path="model.pt", settings_obj=settings_obj)

    assert detector.model == mock_model_instance
    assert detector.conf_threshold == settings_obj.yolo_model.confidence_threshold
    assert detector.nms_threshold == settings_obj.yolo_model.nms_threshold
    # Values come from settings_obj.bytetrack (track_threshold=0.25, match_threshold=0.95)
    assert detector.track_threshold == settings_obj.bytetrack.track_threshold
    assert detector.match_threshold == settings_obj.bytetrack.match_threshold
    assert detector.track_buffer == 60
    # Verify class names were extracted
    assert detector.class_names == {0: "aqua", 1: "zebrafish"}


def test_ultralytics_detector_init_without_settings(mock_ultralytics_import):
    """Test initialization without settings object (fallback defaults)."""
    mock_model_instance = MagicMock()
    mock_model_instance.names = {0: "aqua", 1: "zebrafish"}  # Add class names
    mock_ultralytics_import.return_value = mock_model_instance

    detector = UltralyticsDetectorPlugin(model_path="model.pt", settings_obj=None)

    assert detector.model == mock_model_instance
    assert detector.conf_threshold == 0.25
    assert detector.nms_threshold == 0.45
    # Fallback defaults when settings not injected (match settings.py)
    assert detector.track_threshold == 0.25
    assert detector.match_threshold == 0.95


def test_ultralytics_detector_init_path_object(mock_ultralytics_import):
    """Test initialization with Path object."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    path = Path("model.pt")
    UltralyticsDetectorPlugin(model_path=path, settings_obj=None)

    mock_ultralytics_import.assert_called_once_with(str(path))


def test_ultralytics_detector_import_error():
    """Test that import error is raised when ultralytics is not available."""
    with patch("zebtrack.plugins.ultralytics_detector.ULTRALYTICS_AVAILABLE", False):
        with pytest.raises(ImportError, match="Ultralytics is not available"):
            UltralyticsDetectorPlugin(model_path="model.pt")


def test_ultralytics_detector_model_input_shape(mock_ultralytics_import):
    """Test that model_input_shape property returns correct value."""
    mock_model_instance = MagicMock()
    mock_model_instance.args.imgsz = (640, 640)
    mock_ultralytics_import.return_value = mock_model_instance

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    shape = detector.model_input_shape

    assert isinstance(shape, tuple)
    assert len(shape) == 2
    assert shape == (640, 640)
    assert all(isinstance(x, int) for x in shape)


def test_ultralytics_detector_detect_with_results(mock_ultralytics_import):
    """Test detect method with successful detections."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock result
    mock_boxes = MagicMock()
    mock_boxes.xyxy.cpu().numpy.return_value = np.array([[100, 200, 300, 400], [50, 60, 150, 160]])
    mock_boxes.conf.cpu().numpy.return_value = np.array([0.95, 0.85])
    mock_boxes.cls.cpu().numpy.return_value = np.array([0, 0])

    mock_result = MagicMock()
    mock_result.boxes = mock_boxes

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)

    assert len(detections) == 2

    # Check first detection
    x1, y1, x2, y2, conf, track_id, class_id = detections[0]
    assert x1 == 100 and y1 == 200 and x2 == 300 and y2 == 400
    assert conf == 0.95
    assert track_id is None  # Should be None for ByteTrack to assign
    assert class_id == 0

    # Check second detection
    x1, y1, x2, y2, conf, track_id, class_id = detections[1]
    assert x1 == 50 and y1 == 60 and x2 == 150 and y2 == 160
    assert conf == 0.85
    assert track_id is None
    assert class_id == 0


def test_ultralytics_detector_detect_no_boxes(mock_ultralytics_import):
    """Test detect method when no boxes are detected."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock result with no boxes
    mock_result = MagicMock()
    mock_result.boxes = None

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)

    assert detections == []


def test_ultralytics_detector_detect_empty_results(mock_ultralytics_import):
    """Test detect method when results are empty."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    mock_model_instance.predict.return_value = []

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)

    assert detections == []


def test_ultralytics_detector_predict_with_masks(mock_ultralytics_import):
    """Test predict method with segmentation masks."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock box
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock(tolist=lambda: [100, 200, 300, 400])]
    mock_box.cls = 0
    mock_box.conf = 0.95

    # Create mock masks
    mock_masks = MagicMock()
    mock_masks.xy = [np.array([[100, 200], [150, 250], [200, 200]])]

    # Create mock result
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.masks = mock_masks
    mock_result.names = {0: "aquarium"}

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.predict(frame)

    assert len(results) == 1
    assert results[0]["box"] == [100, 200, 300, 400]
    assert results[0]["confidence"] == 0.95
    assert results[0]["class_id"] == 0
    assert results[0]["class_name"] == "aquarium"
    assert results[0]["has_mask"] is True
    assert results[0]["mask_points"] == 3


def test_ultralytics_detector_predict_without_masks(mock_ultralytics_import):
    """Test predict method without segmentation masks."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock box
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock(tolist=lambda: [100, 200, 300, 400])]
    mock_box.cls = 0
    mock_box.conf = 0.95

    # Create mock result
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.masks = None
    mock_result.names = {0: "fish"}

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.predict(frame)

    assert len(results) == 1
    assert results[0]["has_mask"] is False
    assert results[0]["mask_points"] == 0


def test_ultralytics_detector_predict_orphan_masks(mock_ultralytics_import):
    """Test predict method with orphan masks (masks without boxes)."""
    mock_model_instance = MagicMock()
    mock_model_instance.names = {0: "aquarium", 1: "zebrafish"}  # Add class names
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock masks (2 masks but only 1 box)
    mask_xy_1 = np.array([[100, 200], [150, 250], [200, 200]])
    mask_xy_2 = np.array([[300, 400], [350, 450], [400, 400]])

    mock_masks = MagicMock()
    mock_masks.xy = [mask_xy_1, mask_xy_2]

    # Create only 1 box
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock(tolist=lambda: [100, 200, 300, 400])]
    mock_box.cls = 0
    mock_box.conf = 0.95

    # Create mock result
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_result.masks = mock_masks
    mock_result.names = {0: "aquarium"}

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.predict(frame)

    # Should have 2 results: 1 box with mask + 1 orphan mask
    assert len(results) == 2

    # First result is the box with mask
    assert results[0]["box"] == [100, 200, 300, 400]
    assert results[0]["has_mask"] is True

    # Second result is the orphan mask
    assert results[1]["box"] == [300, 400, 400, 450]
    assert results[1]["confidence"] == 0.99
    assert results[1]["class_name"] == "aquarium"
    assert results[1]["has_mask"] is True


def test_ultralytics_detector_get_name():
    """Test get_name static method."""
    assert UltralyticsDetectorPlugin.get_name() == "YOLO (Ultralytics)"


def test_ultralytics_detector_set_tracking_parameters(mock_ultralytics_import):
    """Test set_tracking_parameters method."""
    mock_model_instance = MagicMock()
    mock_model_instance.names = {0: "aqua", 1: "zebrafish"}  # Add class names
    mock_ultralytics_import.return_value = mock_model_instance

    detector = UltralyticsDetectorPlugin(model_path="model.pt")

    # Initial values (match settings.py defaults: track_threshold=0.25, match_threshold=0.95)
    assert detector.track_threshold == 0.25
    assert detector.match_threshold == 0.95

    # Update both parameters
    detector.set_tracking_parameters(track_threshold=0.5, match_threshold=0.3)
    assert detector.track_threshold == 0.5
    assert detector.match_threshold == 0.3

    # Update only track_threshold
    detector.set_tracking_parameters(track_threshold=0.6)
    assert detector.track_threshold == 0.6
    assert detector.match_threshold == 0.3

    # Update only match_threshold
    detector.set_tracking_parameters(match_threshold=0.4)
    assert detector.track_threshold == 0.6
    assert detector.match_threshold == 0.4

    # Test with zero/negative values (should not update)
    detector.set_tracking_parameters(track_threshold=0, match_threshold=-0.1)
    assert detector.track_threshold == 0.6
    assert detector.match_threshold == 0.4


def test_ultralytics_detector_reset_tracking_state(mock_ultralytics_import):
    """Test reset_tracking_state method (no-op for Ultralytics)."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    detector = UltralyticsDetectorPlugin(model_path="model.pt")

    # Should not raise any errors
    detector.reset_tracking_state()


def test_ultralytics_detector_predict_custom_confidence(mock_ultralytics_import):
    """Test predict method with custom confidence threshold."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock result
    mock_result = MagicMock()
    mock_result.boxes = None
    mock_result.masks = None

    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Test with custom confidence
    detector.predict(frame, conf_threshold=0.7)

    mock_model_instance.predict.assert_called_once()
    call_kwargs = mock_model_instance.predict.call_args[1]
    assert call_kwargs["conf"] == 0.7


def test_ultralytics_detector_detect_calls_predict_with_correct_params(
    mock_ultralytics_import, settings_obj
):
    """Test that detect calls predict with correct parameters."""
    mock_model_instance = MagicMock()
    mock_ultralytics_import.return_value = mock_model_instance

    # Create mock result
    mock_result = MagicMock()
    mock_result.boxes = None
    mock_model_instance.predict.return_value = [mock_result]

    detector = UltralyticsDetectorPlugin(model_path="model.pt", settings_obj=settings_obj)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detector.detect(frame)

    # Verify predict was called with correct parameters
    mock_model_instance.predict.assert_called_once()
    call_args = mock_model_instance.predict.call_args
    assert np.array_equal(call_args[0][0], frame)

    call_kwargs = call_args[1]
    assert call_kwargs["verbose"] is False
    assert call_kwargs["conf"] == settings_obj.yolo_model.confidence_threshold
    assert call_kwargs["iou"] == settings_obj.yolo_model.nms_threshold
    assert call_kwargs["classes"] is None
