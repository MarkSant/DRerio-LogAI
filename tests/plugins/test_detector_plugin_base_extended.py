"""Extended unit tests for plugins/base.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from zebtrack.plugins.base import DetectorPlugin


class ConcreteTestDetectorPlugin(DetectorPlugin):
    """Concrete implementation of DetectorPlugin for testing default methods."""

    def __init__(self, model_path: Path | str, **kwargs: Any):
        self.model_path = model_path
        self._detect_calls: list[np.ndarray] = []

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        self._detect_calls.append(frame)
        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        return [(10, 10, 50, 50, conf, 1, 0)]

    @staticmethod
    def get_name() -> str:
        return "TestDetector"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 640)


class TestDetectorPluginBase:
    """Test DetectorPlugin default attributes, mask capture toggle, and batch detection."""

    def test_default_attributes(self):
        plugin = ConcreteTestDetectorPlugin("/path/model.pt")
        assert plugin.conf_threshold == 0.25
        assert plugin.nms_threshold == 0.45
        assert plugin._capture_masks is False
        assert plugin.get_name() == "TestDetector"
        assert plugin.model_input_shape == (640, 640)

    def test_set_mask_capture(self):
        plugin = ConcreteTestDetectorPlugin("/path/model.pt")
        assert plugin._capture_masks is False

        plugin.set_mask_capture(True)
        assert plugin._capture_masks is True

        plugin.set_mask_capture(False)
        assert plugin._capture_masks is False

    def test_pop_frame_masks_default_is_empty_list(self):
        plugin = ConcreteTestDetectorPlugin("/path/model.pt")
        masks = plugin.pop_frame_masks()
        assert masks == []

    def test_detect_batch_iterates_and_aggregates(self):
        plugin = ConcreteTestDetectorPlugin("/path/model.pt")
        f1 = np.zeros((100, 100, 3), dtype=np.uint8)
        f2 = np.ones((100, 100, 3), dtype=np.uint8)

        results = plugin.detect_batch([f1, f2], conf_threshold=0.8)
        assert len(results) == 2
        assert len(plugin._detect_calls) == 2
        assert results[0] == [(10, 10, 50, 50, 0.8, 1, 0)]
        assert results[1] == [(10, 10, 50, 50, 0.8, 1, 0)]
