import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import structlog

from zebtrack.core.detector import Detector, ZoneData
from zebtrack.plugins.base import DetectorPlugin


class MockDetectorPlugin(DetectorPlugin):
    """A more complete mock detector plugin for testing."""
    def __init__(self):
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self.track_buffer = 60
        self.model_input_shape = (480, 640)
        # Add a mock for reset_tracking_state
        self.reset_tracking_state = MagicMock()

    def detect(self, frame: np.ndarray):
        # Return a sample detection
        return [(10, 10, 20, 20, 0.9, None)]

    def get_name(self) -> str:
        return "MockPlugin"


class TestDetector(unittest.TestCase):
    def setUp(self):
        self.plugin = MockDetectorPlugin()
        self.detector = Detector(self.plugin, base_width=640, base_height=480)
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.zones = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])

    def test_detect_without_set_zones_raises_error(self):
        """Test that calling detect() before set_zones() raises a RuntimeError."""
        with self.assertRaises(RuntimeError) as cm:
            self.detector.detect(self.frame, project_type="video")
        self.assertIn("Must call set_zones() before detect()", str(cm.exception))

    def test_detect_with_set_zones_succeeds(self):
        """Test that detect() runs without error after set_zones() is called."""
        self.detector.set_zones(self.zones, actual_width=640, actual_height=480)
        try:
            detections, _ = self.detector.detect(self.frame, project_type="video")
            self.assertIsInstance(detections, list)
        except RuntimeError:
            self.fail("detector.detect() raised RuntimeError unexpectedly!")

    @patch("zebtrack.core.detector.log")
    def test_dimension_mismatch_warning(self, mock_log):
        """Test that a warning is logged if frame dimensions change."""
        self.detector.set_zones(self.zones, actual_width=640, actual_height=480)
        wrong_dimension_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.detector.detect(wrong_dimension_frame, project_type="video")

        mock_log.warning.assert_called_once_with(
            "detector.dimension_mismatch",
            expected=(640, 480),
            actual=(1920, 1080),
        )

    def test_detect_method_exists(self):
        """Test that the Detector class has a 'detect' method and not 'process_frame'."""
        self.assertTrue(hasattr(self.detector, "detect"))
        self.assertFalse(hasattr(self.detector, "process_frame"))


if __name__ == "__main__":
    unittest.main()