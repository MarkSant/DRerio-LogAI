"""Comprehensive tests for plugins/ultralytics_detector.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import zebtrack.plugins.ultralytics_detector as ul_module
from zebtrack.plugins.ultralytics_detector import (
    ULTRALYTICS_AVAILABLE,
    UltralyticsDetectorPlugin,
)
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
    # #666: the plugin no longer pins a buffer, so ByteTrack gets the settings' value.
    from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor

    settings_obj.bytetrack.track_buffer = 240
    assert DetectionPostProcessor.get_track_buffer(settings_obj, detector) == 240
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
    mock_model_instance.predict.reset_mock()  # Reset warm-up call
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
    mock_model_instance.predict.reset_mock()  # Reset warm-up call
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


class TestUltralyticsDetectorExtended:
    @pytest.fixture
    def mock_model(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        fake_model = MagicMock()
        fake_model.names = {0: "aqua", 1: "zebrafish"}
        fake_model.predict.return_value = [SimpleNamespace(boxes=None)]
        fake_yolo = MagicMock(return_value=fake_model)
        monkeypatch.setattr(ul_module, "YOLO", fake_yolo)
        monkeypatch.setattr(ul_module, "ULTRALYTICS_AVAILABLE", True)
        return fake_model

    def test_import_error_when_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(ul_module, "ULTRALYTICS_AVAILABLE", False)
        with pytest.raises(ImportError, match="Ultralytics is not available"):
            UltralyticsDetectorPlugin("dummy.pt")

    def test_metadata_and_input_shape(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")
        assert plugin.get_name() == "YOLO (Ultralytics)"
        assert plugin.model_input_shape == (640, 640)

    def test_reset_tracking_state_noop(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")
        plugin.reset_tracking_state()  # Should execute cleanly without error

    def test_detect_with_boxes(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")

        mock_boxes = MagicMock()
        mock_boxes.xyxy = MagicMock()
        mock_boxes.xyxy.cpu().numpy.return_value = np.array([[10.0, 20.0, 50.0, 60.0]])
        mock_boxes.conf = MagicMock()
        mock_boxes.conf.cpu().numpy.return_value = np.array([0.92])
        mock_boxes.cls = MagicMock()
        mock_boxes.cls.cpu().numpy.return_value = np.array([1.0])

        mock_result = SimpleNamespace(boxes=mock_boxes, masks=None)
        mock_model.predict.return_value = [mock_result]

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        dets = plugin.detect(frame, conf_threshold=0.5)

        assert len(dets) == 1
        x1, y1, x2, y2, conf, track_id, cls_id = dets[0]
        assert (x1, y1, x2, y2) == (10, 20, 50, 60)
        assert pytest.approx(conf, 0.01) == 0.92
        assert track_id is None
        assert cls_id == 1

    def test_detect_with_mask_capture(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")
        plugin.set_mask_capture(True)

        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu().numpy.return_value = np.array([[10.0, 20.0, 50.0, 60.0]])
        mock_boxes.conf.cpu().numpy.return_value = np.array([0.85])
        mock_boxes.cls.cpu().numpy.return_value = np.array([0.0])

        mock_masks = SimpleNamespace(xy=[np.array([[10, 20], [50, 20], [50, 60], [10, 60]])])
        mock_result = SimpleNamespace(boxes=mock_boxes, masks=mock_masks)
        mock_model.predict.return_value = [mock_result]

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        dets = plugin.detect(frame)
        assert len(dets) == 1

        masks = plugin.pop_frame_masks()
        assert len(masks) == 1
        assert masks[0] is not None
        assert masks[0].shape == (4, 2)

        # Second pop is empty
        assert plugin.pop_frame_masks() == []

    def test_predict_diagnostic_with_boxes_and_orphan_masks(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")

        mock_box = MagicMock()
        mock_box.xyxy = [np.array([10.0, 10.0, 40.0, 40.0])]
        mock_box.cls = 1.0
        mock_box.conf = 0.95

        # 1 box and 2 masks (second mask is an orphan)
        mock_masks = SimpleNamespace(
            xy=[
                np.array([[10, 10], [40, 10], [40, 40]]),
                np.array([[100, 100], [200, 100], [200, 200], [100, 200]]),
            ]
        )

        mock_result = SimpleNamespace(
            boxes=[mock_box],
            masks=mock_masks,
            names={0: "aqua", 1: "zebrafish"},
        )
        mock_model.predict.return_value = [mock_result]

        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        diag = plugin.predict(frame)

        assert len(diag) == 2
        # First item from box
        assert diag[0]["class_name"] == "zebrafish"
        assert diag[0]["has_mask"] is True
        assert diag[0]["mask_points"] == 3

        # Second item from orphan mask
        assert diag[1]["class_name"] == "aqua"
        assert diag[1]["has_mask"] is True
        assert diag[1]["box"] == [100, 100, 200, 200]

    def test_detect_batch_empty_and_populated(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")
        assert plugin.detect_batch([]) == []

        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu().numpy.return_value = np.array([[5.0, 5.0, 25.0, 25.0]])
        mock_boxes.conf.cpu().numpy.return_value = np.array([0.90])
        mock_boxes.cls.cpu().numpy.return_value = np.array([0.0])

        mock_result1 = SimpleNamespace(boxes=mock_boxes)
        mock_result2 = SimpleNamespace(boxes=None)
        mock_model.predict.return_value = [mock_result1, mock_result2]

        frames = [np.zeros((50, 50, 3), dtype=np.uint8), np.zeros((50, 50, 3), dtype=np.uint8)]
        batch_res = plugin.detect_batch(frames)

        assert len(batch_res) == 2
        assert len(batch_res[0]) == 1
        assert len(batch_res[1]) == 0


class TestUltralyticsDetectorExtended2:
    def test_ultralytics_availability_boolean(self):
        assert isinstance(ULTRALYTICS_AVAILABLE, bool)

    def test_initialization_with_mocked_yolo(self):
        with (
            patch("zebtrack.plugins.ultralytics_detector.YOLO") as mock_yolo_cls,
            patch("zebtrack.plugins.ultralytics_detector.is_cuda_available", return_value=False),
        ):
            mock_model = MagicMock()
            mock_model.names = {0: "aquarium", 1: "zebrafish"}
            mock_yolo_cls.return_value = mock_model

            plugin = UltralyticsDetectorPlugin("weights.pt", settings_obj=None)
            assert plugin.class_names == {0: "aquarium", 1: "zebrafish"}
            assert plugin.conf_threshold == 0.25
            assert plugin.nms_threshold == 0.45
            assert plugin.track_threshold == 0.25
            assert plugin.match_threshold == 0.95
            # #666: the ByteTrack buffer is the settings' to decide, never the plugin's.
            assert not hasattr(plugin, "track_buffer")
            assert plugin._half_enabled is False

    def test_initialization_with_injected_settings(self):
        settings = MagicMock()
        settings.yolo_model.confidence_threshold = 0.60
        settings.yolo_model.nms_threshold = 0.50
        settings.yolo_model.use_half_precision = False
        settings.yolo_model.inference_size = 320
        settings.yolo_model.device = "cpu"
        settings.bytetrack.track_threshold = 0.30
        settings.bytetrack.match_threshold = 0.85

        with (
            patch("zebtrack.plugins.ultralytics_detector.YOLO") as mock_yolo_cls,
            patch("zebtrack.plugins.ultralytics_detector.is_cuda_available", return_value=False),
        ):
            mock_model = MagicMock()
            mock_model.names = {0: "fish"}
            mock_yolo_cls.return_value = mock_model

            plugin = UltralyticsDetectorPlugin("weights.pt", settings_obj=settings)
            assert plugin.conf_threshold == 0.60
            assert plugin.nms_threshold == 0.50
            assert plugin.track_threshold == 0.30
            assert plugin.match_threshold == 0.85
            assert plugin._imgsz == 320
            assert plugin._half_enabled is False


@pytest.fixture
def fake_ultralytics(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace YOLO so __init__ does not load weights from disk."""
    fake_model = MagicMock()
    fake_model.names = {0: "aquarium", 1: "zebrafish"}
    fake_model.predict.return_value = [SimpleNamespace(boxes=None)]
    fake_yolo = MagicMock(return_value=fake_model)
    monkeypatch.setattr(ul_module, "YOLO", fake_yolo)
    monkeypatch.setattr(ul_module, "ULTRALYTICS_AVAILABLE", True)
    return fake_model


def _settings(device: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        yolo_model=SimpleNamespace(
            confidence_threshold=0.4,
            nms_threshold=0.5,
            use_half_precision=True,
            inference_size=640,
            device=device,
        ),
        bytetrack=SimpleNamespace(track_threshold=0.3, match_threshold=0.9),
    )


def test_device_none_is_not_passed_to_predict(fake_ultralytics: MagicMock) -> None:
    """Default behavior: do not pass device kwarg so Ultralytics auto-selects."""
    plugin = ul_module.UltralyticsDetectorPlugin(
        model_path="dummy.pt", settings_obj=_settings(None)
    )
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    args, kwargs = fake_ultralytics.predict.call_args
    assert "device" not in kwargs


def test_device_cpu_propagates_and_disables_half(fake_ultralytics: MagicMock) -> None:
    """device='cpu' → kwarg flows through; FP16 forced off (CPU does not benefit)."""
    plugin = ul_module.UltralyticsDetectorPlugin(
        model_path="dummy.pt", settings_obj=_settings("cpu")
    )
    assert plugin._half_enabled is False
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    _args, kwargs = fake_ultralytics.predict.call_args
    assert kwargs["device"] == "cpu"
    assert kwargs["half"] is False


def test_device_cuda_enables_half_only_when_cuda_available(
    fake_ultralytics: MagicMock,
) -> None:
    """device='cuda:0' propagates; FP16 reflects real CUDA availability."""
    with patch.object(ul_module, "is_cuda_available", return_value=True):
        plugin = ul_module.UltralyticsDetectorPlugin(
            model_path="dummy.pt", settings_obj=_settings("cuda:0")
        )

    assert plugin._half_enabled is True
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    _args, kwargs = fake_ultralytics.predict.call_args
    assert kwargs["device"] == "cuda:0"
    assert kwargs["half"] is True


def test_device_cuda_with_no_runtime_cuda_disables_half(
    fake_ultralytics: MagicMock,
) -> None:
    """User asked for CUDA but runtime cannot provide it → FP16 must stay off."""
    with patch.object(ul_module, "is_cuda_available", return_value=False):
        plugin = ul_module.UltralyticsDetectorPlugin(
            model_path="dummy.pt", settings_obj=_settings("cuda:0")
        )

    assert plugin._half_enabled is False
