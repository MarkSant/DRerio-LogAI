import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.detector import Detector
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings


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
        self.detector = Detector(plugin=self.mock_plugin)

    def test_initialization(self):
        """Test that the detector initializes correctly with a plugin."""
        self.assertIsNotNone(self.detector)
        self.assertEqual(self.detector.plugin, self.mock_plugin)
        self.assertEqual(self.detector.flag, 0)

    def test_initialization_fails_without_plugin(self):
        """Test that Detector raises an error if no plugin is provided."""
        with self.assertRaises(ValueError):
            Detector(plugin=None)

    def test_update_scaling(self):
        """Test the logic for scaling detection zones."""
        base_width = settings.camera.desired_width
        base_height = settings.camera.desired_height
        test_width, test_height = 640, 360
        self.detector.update_scaling(test_width, test_height)
        scale_x = test_width / base_width
        scale_y = test_height / base_height
        original_point = self.detector.base_polygon[0]
        scaled_point = self.detector.scaled_polygon[0]
        expected_x = int(original_point[0] * scale_x)
        expected_y = int(original_point[1] * scale_y)
        self.assertEqual(scaled_point[0], expected_x)
        self.assertEqual(scaled_point[1], expected_y)

    def test_process_frame_delegates_to_plugin(self):
        """Test that process_frame calls the plugin's detect method."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.mock_plugin.detect = MagicMock(return_value=[])
        self.detector.process_frame(dummy_frame, "live")
        self.mock_plugin.detect.assert_called_once_with(dummy_frame)

    def test_is_inside_square(self):
        """Test the _is_inside_square helper method."""
        square = ((100, 100), (200, 200))
        self.assertTrue(self.detector._is_inside_square(110, 110, 190, 190, square))
        self.assertTrue(self.detector._is_inside_square(150, 150, 250, 250, square))
        self.assertFalse(self.detector._is_inside_square(300, 300, 400, 400, square))

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

    def test_state_machine_logic(self):
        """Test the command generation logic based on state."""
        # Setup: A detection inside the first configured square
        square = settings.detection_zones.squares[0]
        x_c = (square[0][0] + square[1][0]) // 2
        y_c = (square[0][1] + square[1][1]) // 2
        dummy_frame = np.zeros(
            (settings.camera.desired_height, settings.camera.desired_width, 3),
            dtype=np.uint8,
        )

        # --- Step 1: Object enters a square, should generate ENTER command ---
        # Detection now includes a track_id
        fake_detection = [(x_c - 5, y_c - 5, x_c + 5, y_c + 5, 0.9, 1)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

        self.assertEqual(self.detector.flag, 1, "Flag should be 1 (waiting for exit)")
        self.assertEqual(self.detector.current_square, 1)
        self.assertEqual(command, settings.detection_zones.enter_commands[0])
        # Also check that the returned detection includes the track_id
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0][-1], 1)

        # --- Step 2: Object is still inside, should generate NO command ---
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")
        self.assertIsNone(
            command, "No command should be sent if object is still inside"
        )

        # --- Step 3: Object moves outside all squares, should generate EXIT command ---
        # Detection now includes a track_id
        self.mock_plugin.set_detect_return_value([(10, 10, 20, 20, 0.9, 2)])
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

        self.assertEqual(self.detector.flag, 0, "Flag should reset to 0")
        self.assertEqual(self.detector.current_square, 0)
        self.assertEqual(command, settings.detection_zones.exit_commands[0])
        self.assertEqual(detections[0][-1], 2)


if __name__ == "__main__":
    unittest.main()
