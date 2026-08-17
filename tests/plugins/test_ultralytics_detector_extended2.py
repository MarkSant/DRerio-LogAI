"""Extended unit tests for plugins/ultralytics_detector.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.plugins.ultralytics_detector import (
    ULTRALYTICS_AVAILABLE,
    UltralyticsDetectorPlugin,
)


class TestUltralyticsDetectorExtended2:
    """Test UltralyticsDetectorPlugin initialization and fallback parameters."""

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
            assert plugin.track_buffer == 60
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
