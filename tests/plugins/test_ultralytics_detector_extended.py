"""
Extended unit tests for UltralyticsDetectorPlugin in plugins/ultralytics_detector.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import zebtrack.plugins.ultralytics_detector as ul_module
from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin


class TestUltralyticsDetectorExtended:
    """Test UltralyticsDetectorPlugin detection, batching, masks, and diagnostic mode."""

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

    def test_set_tracking_parameters(self, mock_model: MagicMock):
        plugin = UltralyticsDetectorPlugin("dummy.pt")
        plugin.set_tracking_parameters(track_threshold=0.42, match_threshold=0.88)
        assert plugin.track_threshold == 0.42
        assert plugin.match_threshold == 0.88

        # Non-positive values ignored
        plugin.set_tracking_parameters(track_threshold=-1.0, match_threshold=0.0)
        assert plugin.track_threshold == 0.42
        assert plugin.match_threshold == 0.88

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
