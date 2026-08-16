"""
Extended unit tests for DetectorPlugin base class in plugins/base.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from zebtrack.plugins.base import DetectorPlugin


class ConcreteDetectorPlugin(DetectorPlugin):
    """Concrete implementation of DetectorPlugin for testing default base methods."""

    def __init__(self, model_path: Path | str, **kwargs):
        self.model_path = model_path
        self.detect_call_count = 0

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        self.detect_call_count += 1
        return [(0, 0, 10, 10, 0.95, None, 0)]

    @staticmethod
    def get_name() -> str:
        return "ConcreteDetector"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 640)


class TestBaseDetectorPluginExtended:
    """Test DetectorPlugin default implementations."""

    def test_default_attributes(self):
        plugin = ConcreteDetectorPlugin("model.pt")
        assert plugin.conf_threshold == 0.25
        assert plugin.nms_threshold == 0.45
        assert plugin._capture_masks is False
        assert plugin.pop_frame_masks() == []

    def test_set_mask_capture(self):
        plugin = ConcreteDetectorPlugin("model.pt")
        plugin.set_mask_capture(True)
        assert plugin._capture_masks is True
        plugin.set_mask_capture(False)
        assert plugin._capture_masks is False

    def test_detect_batch_fallback_and_mask_drop(self):
        plugin = ConcreteDetectorPlugin("model.pt")
        plugin.pop_frame_masks = MagicMock(return_value=[])  # type: ignore[method-assign]

        frames = [np.zeros((10, 10, 3)), np.zeros((10, 10, 3)), np.zeros((10, 10, 3))]
        results = plugin.detect_batch(frames, conf_threshold=0.8)

        assert len(results) == 3
        assert plugin.detect_call_count == 3
        # Verified mask drop on multi-frame batches
        plugin.pop_frame_masks.assert_called_once()
