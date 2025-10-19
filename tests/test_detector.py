import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.detector import Detector, ZoneData
from zebtrack.plugins.base import DetectorPlugin


class MockDetectorPlugin(DetectorPlugin):
    """A mock plugin for testing the main Detector class."""

    def __init__(self, model_path: str = "mock_model"):
        self.model_path = model_path
        self._detect_return_value = []
        self.single_subject_mode = False

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

    def set_use_single_subject_mode(self, enabled: bool) -> None:
        self.single_subject_mode = bool(enabled)


class TestDetector(unittest.TestCase):
    def setUp(self):
        """Set up a detector instance with a mock plugin for tests."""
        self.mock_plugin = MockDetectorPlugin()
        self.detector = Detector(plugin=self.mock_plugin, base_width=1280, base_height=720)

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
        mock_zones = ZoneData(
            polygon=[[10, 20], [100, 200]],
            roi_polygons=[[[0, 0], [10, 0], [10, 10], [0, 10]]],
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

    def test_detect_delegates_to_plugin(self):
        """Test that detect calls the plugin's detect method."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(ZoneData(polygon=[[0, 0], [1, 1]]), 640, 480)
        self.mock_plugin.detect = MagicMock(return_value=[])
        self.detector.detect(dummy_frame, "live")
        self.mock_plugin.detect.assert_called()

    def test_set_single_subject_mode_configures_plugin(self):
        self.detector.set_single_subject_mode(True)
        self.assertTrue(self.mock_plugin.single_subject_mode)

        self.detector.set_single_subject_mode(False)
        self.assertFalse(self.mock_plugin.single_subject_mode)

    def test_is_inside_polygon(self):
        """Test the _is_inside_polygon helper method."""
        polygon = np.array([[100, 100], [200, 100], [200, 200], [100, 200]])
        self.assertTrue(self.detector._is_inside_polygon(150, 150, 160, 160, polygon))
        self.assertFalse(self.detector._is_inside_polygon(300, 300, 310, 310, polygon))

    def test_detect_returns_tracked_detections(self):
        """Detector should attach a track_id when plugin returns raw boxes."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(
            ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]), 640, 480
        )
        fake_detection = [(150, 150, 160, 160, 0.9, None)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        # Mock the polygon check to always be true for this test
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, _ = self.detector.detect(dummy_frame, "pre-recorded")

        self.assertEqual(len(detections), 1)
        x1, y1, x2, y2, confidence, track_id = detections[0]
        self.assertIsInstance(track_id, int)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertGreater(x2, x1)
        self.assertGreater(y2, y1)

    def test_single_subject_mode_assigns_constant_track_id(self):
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(
            ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]), 640, 480
        )
        self.detector.set_single_subject_mode(True)

        detections_frame1 = [
            (10, 10, 30, 30, 0.6, None),
            (100, 100, 120, 120, 0.9, None),
        ]

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value(detections_frame1)
            results1, _ = self.detector.detect(dummy_frame, "pre-recorded")

        self.assertEqual(len(results1), 1)
        self.assertEqual(results1[0][5], 1)
        self.assertEqual(results1[0][:4], (100, 100, 120, 120))

        detections_frame2 = [
            (102, 102, 122, 122, 0.55, None),
            (300, 300, 330, 330, 0.99, None),
        ]

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value(detections_frame2)
            results2, _ = self.detector.detect(dummy_frame, "pre-recorded")

        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0][5], 1)
        self.assertEqual(results2[0][:4], (102, 102, 122, 122))

    def test_reset_tracking_state_clears_single_subject_tracker(self):
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(
            ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]), 640, 480
        )
        self.detector.set_single_subject_mode(True)

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value([(50, 50, 80, 80, 0.8, None)])
            self.detector.detect(dummy_frame, "pre-recorded")

        self.detector.reset_tracking_state()

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value([(300, 300, 320, 320, 0.7, None)])
            results, _ = self.detector.detect(dummy_frame, "pre-recorded")

        self.assertEqual(results[0][:4], (300, 300, 320, 320))

    def test_detect_with_empty_polygon(self):
        """
        Tests that detect runs without error and returns no detections
        if the detection polygon is empty.
        """
        # Setup detector with a zone config that has an empty polygon
        empty_polygon_zones = ZoneData(polygon=[])
        self.detector.set_zones(empty_polygon_zones, 1280, 720)

        # Simulate the plugin finding one object
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        fake_detection = [(150, 150, 160, 160, 0.9, 123)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        # Process the frame. This should not raise an exception.
        detections, command = self.detector.detect(dummy_frame, "pre-recorded")

        # Assert that no detections are returned because none can be "inside"
        # the empty polygon.
        self.assertEqual(len(detections), 0)
        self.assertIsNone(command)

    def test_is_inside_polygon_four_corners_or_center(self):
        """Test the _is_inside_polygon method with 4 corners OR center logic."""
        polygon = np.array([[100, 100], [200, 100], [200, 200], [100, 200]])

        # Test case 1: center inside, all corners outside
        # bbox: x1=50, y1=50, x2=90, y2=90 (all corners outside)
        # center: (70, 70) - outside
        self.assertFalse(self.detector._is_inside_polygon(50, 50, 90, 90, polygon))

        # Test case 2: center inside, some corners outside
        # bbox: x1=80, y1=80, x2=120, y2=120
        # center: (100, 100) - outside, but corner (120, 120) inside
        self.assertTrue(self.detector._is_inside_polygon(80, 80, 120, 120, polygon))

        # Test case 3: only one corner inside
        # bbox: x1=90, y1=90, x2=110, y2=110
        # corner (110, 110) is inside
        self.assertTrue(self.detector._is_inside_polygon(90, 90, 110, 110, polygon))

        # Test case 4: center inside, corners outside
        # bbox: x1=140, y1=140, x2=160, y2=160
        # center: (150, 150) inside
        self.assertTrue(self.detector._is_inside_polygon(140, 140, 160, 160, polygon))

        # Test case 5: all points outside
        # bbox: x1=250, y1=250, x2=300, y2=300
        self.assertFalse(self.detector._is_inside_polygon(250, 250, 300, 300, polygon))

        # Test case 6: empty polygon
        empty_polygon = np.array([])
        self.assertFalse(self.detector._is_inside_polygon(150, 150, 160, 160, empty_polygon))

    def test_bbox_hits_roi_polygon_helper(self):
        """Test the bbox_hits_roi_polygon helper method."""
        roi_polygon = np.array([[50, 50], [100, 50], [100, 100], [50, 100]])

        # Test case 1: bbox completely inside
        self.assertTrue(self.detector.bbox_hits_roi_polygon(60, 60, 90, 90, roi_polygon))

        # Test case 2: bbox completely outside
        self.assertFalse(self.detector.bbox_hits_roi_polygon(200, 200, 250, 250, roi_polygon))

        # Test case 3: only center inside
        self.assertTrue(self.detector.bbox_hits_roi_polygon(70, 70, 80, 80, roi_polygon))

        # Test case 4: empty ROI polygon
        empty_roi = np.array([])
        self.assertFalse(self.detector.bbox_hits_roi_polygon(75, 75, 85, 85, empty_roi))

    def test_set_zones_with_invalid_dimensions_raises_error(self):
        """Test that set_zones raises ValueError for non-positive dimensions."""
        zones = ZoneData(polygon=[[0, 0], [1, 1]])
        with self.assertRaisesRegex(ValueError, "Actual dimensions must be positive"):
            self.detector.set_zones(zones, 0, 720)
        with self.assertRaisesRegex(ValueError, "Actual dimensions must be positive"):
            self.detector.set_zones(zones, 1280, -1)

    def test_detect_raises_error_if_zones_not_configured(self):
        """Test that detect() raises RuntimeError if set_zones() is not called."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with self.assertRaisesRegex(
            RuntimeError,
            r"Must call set_zones\(\) before detect\(\)\. "
            r"Zones need video dimensions for proper scaling\.",
        ):
            self.detector.detect(dummy_frame, "live")

    def test_detect_succeeds_after_set_zones(self):
        """Test that detect() succeeds after set_zones() is called."""
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        zones = ZoneData(polygon=[[0, 0], [1, 1]])
        self.detector.set_zones(zones, 640, 480)
        try:
            self.detector.detect(dummy_frame, "live")
        except RuntimeError:
            self.fail("detect() raised RuntimeError unexpectedly!")

    def test_detect_logs_warning_on_dimension_mismatch(self):
        """Test that a warning is logged if frame dimensions change."""
        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        zones = ZoneData(polygon=[[0, 0], [1, 1]])
        self.detector.set_zones(zones, 640, 480)

        with patch("zebtrack.core.detector.log.warning") as mock_log:
            self.detector.detect(dummy_frame, "live")
            mock_log.assert_called_once_with(
                "detector.dimension_mismatch",
                expected=(640, 480),
                actual=(1920, 1080),
                message=(
                    "Frame dimensions differ from dimensions used to set zones. "
                    "This may cause inaccurate detection scaling."
                ),
            )


if __name__ == "__main__":
    unittest.main()
