import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.detector import Detector
from zebtrack.plugins.base import DetectorPlugin


class MockDetectorPlugin(DetectorPlugin):
    """A mock plugin for testing the main Detector class."""

    def __init__(self, model_path: str = "mock_model"):
        self.model_path = model_path
        self._detect_return_value = []

    def detect(self, frame: np.ndarray):
        # Allow configuring the return value for different test cases
        return self._detect_return_value

    @staticmethod
    def get_name() -> str:
        return "Mock Plugin"

    @property
    def model_input_shape(self):
        return (640, 480)

    # Test helper to configure the mock's output
    def set_detect_return_value(self, value):
        self._detect_return_value = value


class TestDetector(unittest.TestCase):
    def setUp(self):
        """Set up a detector instance with a mock plugin for tests."""
        self.mock_plugin = MockDetectorPlugin()
        self.detector = Detector(
            plugin=self.mock_plugin, base_width=1280, base_height=720
        )

    def test_initialization(self):
        """Test that the detector initializes correctly with a plugin."""
        self.assertIsNotNone(self.detector)
        self.assertEqual(self.detector.plugin, self.mock_plugin)

    def test_initialization_fails_without_plugin(self):
        """Test that Detector raises an error if no plugin is provided."""
        with self.assertRaises(ValueError):
            Detector(plugin=None, base_width=1280, base_height=720)

    def test_update_scaling(self):
        """Test the logic for scaling detection zones."""
        from zebtrack.core.detector import ZoneData

        mock_zones = ZoneData(
            polygon=[[10, 20], [100, 200]],
            roi_polygons=[[[0, 0], [10, 0], [10, 10], [0, 10]]]
        )
        test_width, test_height = 640, 360

        self.detector.set_zones(
            zones=mock_zones, actual_width=test_width, actual_height=test_height
        )

        scale_x = test_width / self.detector.base_width
        scale_y = test_height / self.detector.base_height

        # Test main polygon scaling
        original_point = mock_zones.polygon[0]
        scaled_point = self.detector.scaled_polygon[0]
        self.assertEqual(scaled_point[0], int(original_point[0] * scale_x))
        self.assertEqual(scaled_point[1], int(original_point[1] * scale_y))

        # Test ROI polygon scaling
        original_roi_point = mock_zones.roi_polygons[0][1]
        scaled_roi_point = self.detector.scaled_roi_polygons[0][1]
        self.assertEqual(scaled_roi_point[0], int(original_roi_point[0] * scale_x))
        self.assertEqual(scaled_roi_point[1], int(original_roi_point[1] * scale_y))

    def test_process_frame_delegates_to_plugin(self):
        """Test that process_frame calls the plugin's detect method."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.mock_plugin.detect = MagicMock(return_value=[])
        self.detector.process_frame(dummy_frame, "live")
        self.mock_plugin.detect.assert_called_once_with(dummy_frame)

    def test_is_inside_polygon(self):
        """Test the _is_inside_polygon helper method."""
        polygon = np.array([[100, 100], [200, 100], [200, 200], [100, 200]])
        self.assertTrue(self.detector._is_inside_polygon(150, 150, 160, 160, polygon))
        self.assertFalse(self.detector._is_inside_polygon(300, 300, 310, 310, polygon))

    def test_process_frame_returns_correct_format(self):
        """Test that process_frame returns detections with track_id."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Detection now includes a track_id (e.g., 123)
        fake_detection = [(150, 150, 160, 160, 0.9, 123)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        # Mock the polygon check to always be true for this test
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, _ = self.detector.process_frame(dummy_frame, "pre-recorded")

        self.assertEqual(len(detections), 1)
        # Assert that the entire tuple, including track_id, is passed through
        self.assertEqual(detections[0], (150, 150, 160, 160, 0.9, 123))

    def test_process_frame_with_empty_polygon(self):
        """
        Tests that process_frame runs without error and returns no detections
        if the detection polygon is empty.
        """
        from zebtrack.core.detector import ZoneData

        # Setup detector with a zone config that has an empty polygon
        empty_polygon_zones = ZoneData(polygon=[])
        self.detector.set_zones(empty_polygon_zones, 1280, 720)

        # Simulate the plugin finding one object
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        fake_detection = [(150, 150, 160, 160, 0.9, 123)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        # Process the frame. This should not raise an exception.
        detections, command = self.detector.process_frame(dummy_frame, "pre-recorded")

        # Assert that no detections are returned because none can be "inside"
        # the empty polygon.
        self.assertEqual(len(detections), 0)
        self.assertIsNone(command)


if __name__ == "__main__":
    unittest.main()
