"""Comprehensive tests for plugins/base.py."""

from __future__ import annotations

from abc import ABCMeta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.plugins.base import DetectorPlugin


def test_detector_plugin_is_abstract():
    """Test that DetectorPlugin is an abstract base class."""
    assert isinstance(DetectorPlugin, ABCMeta)


def test_detector_plugin_cannot_be_instantiated():
    """Test that DetectorPlugin cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        DetectorPlugin(model_path="dummy.pt")  # type: ignore[abstract]


def test_detector_plugin_requires_init():
    """Test that subclasses must implement __init__."""

    class IncompleteDetector1(DetectorPlugin):
        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            return []

        @staticmethod
        def get_name() -> str:
            return "Incomplete"

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (640, 640)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteDetector1(model_path="dummy.pt")  # type: ignore[abstract]


def test_detector_plugin_requires_detect():
    """Test that subclasses must implement detect method."""

    class IncompleteDetector2(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = model_path

        @staticmethod
        def get_name() -> str:
            return "Incomplete"

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (640, 640)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteDetector2(model_path="dummy.pt")  # type: ignore[abstract]


def test_detector_plugin_requires_get_name():
    """Test that subclasses must implement get_name method."""

    class IncompleteDetector3(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = model_path

        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            return []

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (640, 640)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteDetector3(model_path="dummy.pt")  # type: ignore[abstract]


def test_detector_plugin_requires_model_input_shape():
    """Test that subclasses must implement model_input_shape property."""

    class IncompleteDetector4(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = model_path

        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            return []

        @staticmethod
        def get_name() -> str:
            return "Incomplete"

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteDetector4(model_path="dummy.pt")  # type: ignore[abstract]


def test_detector_plugin_complete_implementation():
    """Test that a complete implementation can be instantiated."""

    class CompleteDetector(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = str(Path(model_path) if isinstance(model_path, str) else model_path)

        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            # Return dummy detection
            return [(100, 100, 200, 200, 0.95, None, 0)]

        @staticmethod
        def get_name() -> str:
            return "Complete Detector"

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (640, 640)

    # Should not raise
    detector = CompleteDetector(model_path="dummy.pt")
    assert detector.model_path == "dummy.pt"
    assert detector.get_name() == "Complete Detector"
    assert detector.model_input_shape == (640, 640)

    # Test detect returns expected format
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)
    assert isinstance(detections, list)
    assert len(detections) == 1
    assert detections[0] == (100, 100, 200, 200, 0.95, None, 0)


def test_detector_plugin_detect_return_type():
    """Test that detect returns list of tuples with correct structure."""

    class TestDetector(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = model_path

        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            return [
                (10, 20, 30, 40, 0.9, 1, 0),  # Detection with track_id
                (50, 60, 70, 80, 0.8, None, 0),  # Detection without track_id
            ]

        @staticmethod
        def get_name() -> str:
            return "Test Detector"

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (416, 416)

    detector = TestDetector(model_path="test.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(frame)

    assert len(detections) == 2

    # Check first detection
    x1, y1, x2, y2, conf, track_id, class_id = detections[0]
    assert x1 == 10 and y1 == 20 and x2 == 30 and y2 == 40
    assert conf == 0.9
    assert track_id == 1
    assert class_id == 0

    # Check second detection
    x1, y1, x2, y2, conf, track_id, class_id = detections[1]
    assert x1 == 50 and y1 == 60 and x2 == 70 and y2 == 80
    assert conf == 0.8
    assert track_id is None
    assert class_id == 0


def test_detector_plugin_accepts_path_object():
    """Test that model_path can be a Path object."""

    class PathDetector(DetectorPlugin):
        def __init__(self, model_path: Path | str):
            self.model_path = Path(model_path) if isinstance(model_path, str) else model_path

        def detect(
            self, frame: np.ndarray, conf_threshold: float | None = None
        ) -> list[tuple[int, int, int, int, float, int | None, int]]:
            return []

        @staticmethod
        def get_name() -> str:
            return "Path Detector"

        @property
        def model_input_shape(self) -> tuple[int, int]:
            return (640, 640)

    # Test with string
    detector1 = PathDetector(model_path="model.pt")
    assert isinstance(detector1.model_path, Path)

    # Test with Path object
    detector2 = PathDetector(model_path=Path("model.pt"))
    assert isinstance(detector2.model_path, Path)


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


class TestByteTrackThresholdHints:
    """#698: both plugins expose the same hints, from the settings or the shared defaults."""

    def test_settings_values_are_copied(self):
        from types import SimpleNamespace

        from zebtrack.plugins.base import bytetrack_threshold_hints

        settings_obj = SimpleNamespace(
            bytetrack=SimpleNamespace(track_threshold=0.3, match_threshold=0.85)
        )
        assert bytetrack_threshold_hints(settings_obj) == (0.3, 0.85)

    def test_without_settings_the_shared_defaults(self):
        from types import SimpleNamespace

        from zebtrack.plugins.base import bytetrack_threshold_hints
        from zebtrack.settings import DEFAULT_MATCH_THRESHOLD, DEFAULT_TRACK_THRESHOLD

        expected = (DEFAULT_TRACK_THRESHOLD, DEFAULT_MATCH_THRESHOLD)
        assert bytetrack_threshold_hints(None) == expected
        assert bytetrack_threshold_hints(SimpleNamespace()) == expected
        # The OpenVINO plugin used to fall back to 0.80 here.
        assert bytetrack_threshold_hints(None)[1] == 0.95
