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
        self.set_mode_calls = 0

    def detect(self, frame: np.ndarray, conf_threshold: float | None = None):
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
        self.set_mode_calls += 1


class TestDetector(unittest.TestCase):
    def setUp(self):
        """Set up a detector instance with a mock plugin for tests."""
        self.mock_plugin = MockDetectorPlugin()
        self.detector = Detector(plugin=self.mock_plugin, base_width=1280, base_height=720)
        # Set to True to simulate "ready to track" state for most tests
        self.detector.set_aquarium_region_defined(True)

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

    def test_clear_cache_empties_scaling_cache(self):
        """Test that clear_cache() purges the internal scaling cache."""
        # First, populate the cache by calling _update_scaling
        mock_zones = ZoneData(polygon=[[10, 20], [100, 200]])
        self.detector.set_zones(zones=mock_zones, actual_width=640, actual_height=360)

        # Ensure the cache is populated
        self.assertIn((640, 360), self.detector._scaling_cache)
        self.assertGreater(len(self.detector._scaling_cache), 0)

        # Call the method to be tested
        self.detector.clear_cache()

        # Assert that the cache is now empty
        self.assertEqual(len(self.detector._scaling_cache), 0)

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

    def test_set_single_subject_mode_reinitializes_tracker_and_notifies_plugin(self):
        sentinel_tracker = object()
        self.detector._byte_tracker = sentinel_tracker
        self.detector._byte_tracker_params = ("params",)

        self.detector.set_single_subject_mode(True)

        self.assertTrue(self.detector.is_single_subject_mode())
        self.assertIsNone(self.detector._byte_tracker)
        self.assertIsNone(self.detector._byte_tracker_params)
        self.assertEqual(self.mock_plugin.set_mode_calls, 1)

    def test_set_single_subject_mode_noop_when_value_unchanged(self):
        sentinel_tracker = object()
        self.detector._single_subject_mode = True
        self.detector._byte_tracker = sentinel_tracker
        self.detector._byte_tracker_params = ("params",)

        self.detector.set_single_subject_mode(True)

        self.assertIs(self.detector._byte_tracker, sentinel_tracker)
        self.assertEqual(self.mock_plugin.set_mode_calls, 0)

    @patch("zebtrack.tracker.basetrack.BaseTrack.reset_id_counter")
    def test_reset_tracking_state_resets_internal_components(self, reset_id_counter):
        self.mock_plugin.reset_tracking_state = MagicMock()
        sentinel_tracker = MagicMock()
        self.detector._single_subject_tracker = sentinel_tracker
        self.detector._byte_tracker = object()
        self.detector._byte_tracker_params = ("params",)

        self.detector.reset_tracking_state()

        self.mock_plugin.reset_tracking_state.assert_called_once()
        sentinel_tracker.reset.assert_called_once()
        reset_id_counter.assert_called_once()
        self.assertIsNone(self.detector._byte_tracker)
        self.assertIsNone(self.detector._byte_tracker_params)

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
        fake_detection = [(150, 150, 160, 160, 0.9, None, 1)]
        self.mock_plugin.set_detect_return_value(fake_detection)

        # Mock the polygon check to always be true for this test
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, _ = self.detector.detect(dummy_frame, "pre-recorded")

        self.assertEqual(len(detections), 1)
        # Unpack 7 elements (x1, y1, x2, y2, confidence, track_id, class_id)
        x1, y1, x2, y2, confidence, track_id, _ = detections[0]
        self.assertIsInstance(track_id, int)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertGreater(x2, x1)
        self.assertGreater(y2, y1)

    def test_single_subject_mode_assigns_constant_track_id(self):
        """Test that single subject mode maintains a constant track ID across frames.

        In single subject mode, ByteTracker:
        1. Returns only ONE detection per frame (the tracked animal)
        2. Maintains the SAME track ID across frames (ID persistence)
        3. Tracks based on spatial proximity (Kalman filter + IoU/center distance)

        Note: ByteTracker does NOT select by highest confidence on first frame.
        It processes detections in order and uses tracking to maintain consistency.
        """
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(
            ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]), 640, 480
        )
        self.detector.set_single_subject_mode(True)

        # Frame 1: Two detections - ByteTracker will select one and assign track_id=1
        detections_frame1 = [
            (10, 10, 30, 30, 0.6, None, 1),
            (100, 100, 120, 120, 0.9, None, 1),
        ]

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value(detections_frame1)
            results1, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Verify single subject mode returns exactly 1 detection
        self.assertEqual(len(results1), 1)
        # Verify track ID is assigned (should be 1 for first track)
        self.assertEqual(results1[0][5], 1)
        # Store the first detection's bbox to verify tracking continuity
        first_bbox = results1[0][:4]

        # Frame 2: Two detections - one near the tracked position, one far away
        # ByteTracker should maintain tracking of the nearby detection
        near_bbox = (first_bbox[0] + 2, first_bbox[1] + 2, first_bbox[2] + 2, first_bbox[3] + 2)
        detections_frame2 = [
            (*near_bbox, 0.55, None, 1),  # Near previous position
            (300, 300, 330, 330, 0.99, None, 1),  # Far away
        ]

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value(detections_frame2)
            results2, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Verify single detection returned
        self.assertEqual(len(results2), 1)
        # Verify SAME track ID is maintained (key requirement of single subject mode)
        self.assertEqual(results2[0][5], 1)
        # Verify it tracked the nearby detection, not the far one
        result_bbox = results2[0][:4]
        # The tracked bbox should be close to near_bbox (within tracking tolerance)
        self.assertLess(
            abs(result_bbox[0] - near_bbox[0]) + abs(result_bbox[1] - near_bbox[1]),
            50,  # Allow some tolerance for Kalman filter smoothing
            f"Expected tracking to follow nearby detection {near_bbox}, got {result_bbox}",
        )

    def test_reset_tracking_state_clears_single_subject_tracker(self):
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.set_zones(
            ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]), 640, 480
        )
        self.detector.set_single_subject_mode(True)

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value([(50, 50, 80, 80, 0.8, None, 1)])
            self.detector.detect(dummy_frame, "pre-recorded")

        self.detector.reset_tracking_state()

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.mock_plugin.set_detect_return_value([(300, 300, 320, 320, 0.7, None, 1)])
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


class TestDetectorZoneLogic(unittest.TestCase):
    """Extended tests for Detector zone handling and edge cases."""

    def setUp(self):
        """Set up a detector instance with a mock plugin for tests."""
        self.mock_plugin = MockDetectorPlugin()
        self.detector = Detector(plugin=self.mock_plugin, base_width=1280, base_height=720)
        # Set to True to simulate "ready to track" state for most tests
        self.detector.set_aquarium_region_defined(True)

    def test_detect_with_arena_cropping(self):
        """Test that detection crops frame to arena bounding box for optimization."""
        zones = ZoneData(polygon=[[100, 100], [500, 100], [500, 400], [100, 400]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Plugin should receive cropped frame, not full frame
        # The actual crop happens in detect(), but we test it delegates to plugin
        self.mock_plugin.set_detect_return_value([(150, 150, 160, 160, 0.8, None, 1)])

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.detector.detect(dummy_frame, "pre-recorded")

        # Verify plugin.detect was called
        self.mock_plugin.detect = MagicMock(return_value=[(150, 150, 160, 160, 0.8, None, 1)])
        self.mock_plugin.set_detect_return_value([(150, 150, 160, 160, 0.8, None, 1)])

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.detector.detect(dummy_frame, "pre-recorded")

        self.mock_plugin.detect.assert_called()

    def test_detect_filters_multiple_detections_by_polygon(self):
        """Test that only detections inside the polygon are kept."""
        zones = ZoneData(polygon=[[100, 100], [300, 100], [300, 300], [100, 300]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Two detections: one inside the arena bbox, one outside
        # Arena bbox is (50, 50, 150, 150) after scaling from (100,100,300,300) @ 640x480
        fake_detections = [
            (60, 60, 70, 70, 0.9, None, 1),  # Will be inside after crop adjustment
            (200, 200, 210, 210, 0.85, None, 1),  # outside
        ]
        self.mock_plugin.set_detect_return_value(fake_detections)

        # Mock to return True for first (initial filter), False for second (initial filter),
        # then True again for post-ByteTracker filter (only the first detection passed)
        with patch.object(
            self.detector,
            "_is_inside_polygon",
            side_effect=[True, False, True],  # 3 calls: 2 initial + 1 post-ByteTracker
        ):
            detections, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Only the first detection should pass through
        self.assertEqual(len(detections), 1)
        # Coordinates are adjusted by cropping offset, so check track confidence instead
        self.assertGreater(detections[0][4], 0.8)

    def test_multiple_roi_polygons_scaling(self):
        """Test that multiple ROI polygons scale correctly."""
        zones = ZoneData(
            polygon=[[0, 0], [1280, 0], [1280, 720], [0, 720]],
            roi_polygons=[
                [[100, 100], [200, 100], [200, 200], [100, 200]],
                [[300, 300], [400, 300], [400, 400], [300, 400]],
            ],
            roi_names=["ROI_1", "ROI_2"],
            roi_colors=[(255, 0, 0), (0, 255, 0)],
        )

        # Scale down by half
        self.detector.set_zones(zones, 640, 360)

        # Check scaled ROI polygons
        self.assertEqual(len(self.detector.scaled_roi_polygons), 2)

        # First ROI should be scaled
        expected_roi1 = np.array([[50, 50], [100, 50], [100, 100], [50, 100]], dtype=np.int32)
        np.testing.assert_array_equal(self.detector.scaled_roi_polygons[0], expected_roi1)

        # Second ROI should be scaled
        expected_roi2 = np.array([[150, 150], [200, 150], [200, 200], [150, 200]], dtype=np.int32)
        np.testing.assert_array_equal(self.detector.scaled_roi_polygons[1], expected_roi2)

    def test_scaling_cache_hit(self):
        """Test that scaling cache avoids redundant calculations."""
        zones = ZoneData(polygon=[[0, 0], [1280, 0], [1280, 720], [0, 720]])

        # First call should populate cache
        self.detector.set_zones(zones, 640, 360)
        self.assertIn((640, 360), self.detector._scaling_cache)

        # Clear scaled_polygon to check if it's restored from cache
        old_polygon = self.detector.scaled_polygon.copy()

        # Manually trigger _update_scaling with same dimensions
        self.detector._update_scaling(640, 360)

        # Should retrieve from cache
        np.testing.assert_array_equal(self.detector.scaled_polygon, old_polygon)

    def test_scaling_cache_miss(self):
        """Test that different dimensions create new cache entry."""
        zones = ZoneData(polygon=[[0, 0], [1280, 0], [1280, 720], [0, 720]])

        self.detector.set_zones(zones, 640, 360)
        self.assertEqual(len(self.detector._scaling_cache), 1)

        # Different dimensions should create new cache entry
        self.detector._update_scaling(320, 180)
        self.assertEqual(len(self.detector._scaling_cache), 2)
        self.assertIn((320, 180), self.detector._scaling_cache)

    def test_bytetrack_integration_with_detections(self):
        """Test that BYTETracker assigns track IDs and preserves detections."""
        zones = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: One detection (use higher confidence for BYTETracker)
        self.mock_plugin.set_detect_return_value([(100, 100, 120, 120, 0.95, None, 1)])
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections1, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Should assign a track ID
        self.assertGreaterEqual(len(detections1), 1)
        if len(detections1) > 0:
            track_id1 = detections1[0][5]
            self.assertIsNotNone(track_id1)

            # Frame 2: Same detection slightly moved (use higher confidence)
            self.mock_plugin.set_detect_return_value([(105, 105, 125, 125, 0.93, None, 1)])
            with patch.object(self.detector, "_is_inside_polygon", return_value=True):
                detections2, _ = self.detector.detect(dummy_frame, "pre-recorded")

            # Detection should be preserved even if ByteTracker can't confirm track yet
            # ByteTracker may return 0 tracks if the track is in "unconfirmed" state
            # Our passthrough mechanism ensures we still get the detection
            self.assertGreaterEqual(len(detections2), 1)
            if len(detections2) > 0:
                track_id2 = detections2[0][5]
                # Track ID may be None if passthrough was used, or same as before if tracked
                if track_id2 is not None:
                    self.assertEqual(track_id1, track_id2)

    def test_bytetrack_handles_empty_detections(self):
        """Test that BYTETracker handles frames with no detections gracefully."""
        zones = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # First frame with detection to initialize tracker
        self.mock_plugin.set_detect_return_value([(100, 100, 120, 120, 0.9, None, 1)])
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections1, _ = self.detector.detect(dummy_frame, "pre-recorded")
        self.assertEqual(len(detections1), 1)

        # Second frame with no detections
        self.mock_plugin.set_detect_return_value([])
        detections2, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Should return empty list without crashing
        self.assertEqual(len(detections2), 0)

    def test_multiple_animals_tracking(self):
        """Test tracking multiple animals with different track IDs."""
        zones = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: Two detections far apart
        self.mock_plugin.set_detect_return_value(
            [
                (100, 100, 120, 120, 0.9, None, 1),
                (400, 400, 420, 420, 0.85, None, 1),
            ]
        )

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections1, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Should have two different track IDs
        self.assertEqual(len(detections1), 2)
        track_ids = {det[5] for det in detections1}
        self.assertEqual(len(track_ids), 2, "Expected two unique track IDs")

    def test_reset_tracking_state_clears_bytetrack(self):
        """Test that reset_tracking_state() clears BYTETracker."""
        zones = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: Create a track
        self.mock_plugin.set_detect_return_value([(100, 100, 120, 120, 0.9, None, 1)])
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            self.detector.detect(dummy_frame, "pre-recorded")
        # Track ID is assigned but we'll verify the reset behavior below

        # Reset tracking
        self.detector.reset_tracking_state()

        # Frame 2: Same detection should get a new track ID after reset
        self.mock_plugin.set_detect_return_value([(100, 100, 120, 120, 0.9, None, 1)])
        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections2, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # New track ID should be assigned (BYTETracker was reset)
        track_id2 = detections2[0][5]
        # After reset, track IDs may restart
        self.assertIsNotNone(track_id2)

    def test_draw_overlay_renders_polygons(self):
        """Test that draw_overlay draws ROI polygons and detections."""
        zones = ZoneData(
            polygon=[[100, 100], [500, 100], [500, 400], [100, 400]],
            roi_polygons=[[[150, 150], [200, 150], [200, 200], [150, 200]]],
            roi_names=["Test ROI"],
            roi_colors=[(255, 0, 0)],
        )
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = [(200, 200, 220, 220, 0.9, 42)]

        # Should not raise any errors
        try:
            self.detector.draw_overlay(dummy_frame, detections)
        except Exception as e:
            self.fail(f"draw_overlay raised exception: {e}")

    def test_detect_with_non_rectangular_polygon(self):
        """Test detection with complex (non-rectangular) polygon."""
        # Pentagon shape
        zones = ZoneData(polygon=[[320, 100], [500, 200], [450, 400], [190, 400], [140, 200]])
        self.detector.set_zones(zones, 640, 480)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.mock_plugin.set_detect_return_value([(300, 250, 310, 260, 0.8, None, 1)])

        with patch.object(self.detector, "_is_inside_polygon", return_value=True):
            detections, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Should handle complex polygon without issues
        self.assertEqual(len(detections), 1)

    def test_ensure_track_tuple_with_5_elements(self):
        """Test _ensure_track_tuple handles 5-element tuples (no track_id, no class_id)."""
        detection_5 = (100, 150, 200, 250, 0.95)
        result = self.detector._ensure_track_tuple(detection_5)

        self.assertEqual(len(result), 7)
        self.assertEqual(result[:5], (100, 150, 200, 250, 0.95))
        self.assertIsNone(result[5])  # track_id
        self.assertEqual(result[6], 0)  # class_id default

    def test_ensure_track_tuple_with_6_elements(self):
        """Test _ensure_track_tuple handles 6-element tuples (with track_id, no class_id)."""
        detection_6 = (100, 150, 200, 250, 0.92, 42)
        result = self.detector._ensure_track_tuple(detection_6)

        self.assertEqual(len(result), 7)
        self.assertEqual(result[:6], (100, 150, 200, 250, 0.92, 42))
        self.assertEqual(result[6], 0)  # class_id default

    def test_get_track_threshold_from_plugin(self):
        """Test _get_track_threshold retrieves from plugin if available."""
        self.mock_plugin.track_threshold = 0.35
        threshold = self.detector._get_track_threshold()
        self.assertEqual(threshold, 0.35)

    def test_get_match_threshold_from_plugin(self):
        """Test _get_match_threshold retrieves from plugin if available."""
        self.mock_plugin.match_threshold = 0.20
        threshold = self.detector._get_match_threshold()
        self.assertEqual(threshold, 0.20)

    def test_get_track_buffer_from_plugin(self):
        """Test _get_track_buffer retrieves from plugin if available."""
        self.mock_plugin.track_buffer = 45
        buffer = self.detector._get_track_buffer()
        self.assertEqual(buffer, 45)

    def test_detect_class_mismatch_fallback(self):
        """
        Test that small class 0 detections are treated as class 1 (animals)
        when they are significantly smaller than the arena.
        """
        # Define a large arena (1000x1000 = 1,000,000 pixels)
        zones = ZoneData(polygon=[[0, 0], [1000, 0], [1000, 1000], [0, 1000]])
        self.detector.set_zones(zones, 1000, 1000)

        dummy_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)

        # Mock detection: Class 0 (Aquarium), but small (10x10 = 100 pixels)
        # Ratio: 100 / 1,000,000 = 0.0001 (much less than 0.5)
        # Should be converted to Class 1
        small_detection = (500, 500, 510, 510, 0.9, None, 0)

        # Mock detection: Class 0 (Aquarium), large (900x900 = 810,000 pixels)
        # Ratio: 0.81 (greater than 0.5)
        # Should remain Class 0 and be filtered out (since we want class 1)
        large_detection = (50, 50, 950, 950, 0.9, None, 0)

        self.mock_plugin.set_detect_return_value([small_detection, large_detection])

        # Mock ByteTracker to return detections as-is (bypass tracking logic)
        with (
            patch.object(self.detector, "_is_inside_polygon", return_value=True),
            patch.object(
                self.detector, "_apply_byte_tracking", side_effect=lambda dets, shape: dets
            ),
        ):
            detections, _ = self.detector.detect(dummy_frame, "pre-recorded")

        # Only the small detection should be returned (converted to class 1)
        self.assertEqual(len(detections), 1)

        # Verify it was converted to class 1
        x1, y1, x2, y2, _, _, class_id = detections[0]
        self.assertEqual(class_id, 1)
        self.assertEqual((x1, y1, x2, y2), (500, 500, 510, 510))


if __name__ == "__main__":
    unittest.main()
