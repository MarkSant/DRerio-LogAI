import unittest

from zebtrack.core.single_subject_tracker import SingleSubjectTracker


class TestSingleSubjectTracker(unittest.TestCase):
    def test_selects_highest_confidence_initial(self):
        tracker = SingleSubjectTracker()
        detections = [
            (0, 0, 10, 10, 0.3, None, 0),
            (5, 5, 20, 20, 0.8, None, 0),
        ]

        result = tracker.assign(detections)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][:4], (5, 5, 20, 20))
        self.assertEqual(result[0][5], 1)

    def test_prefers_high_iou_over_confidence(self):
        tracker = SingleSubjectTracker()
        tracker.assign([(10, 10, 30, 30, 0.9, None, 0)])

        detections = [
            (12, 12, 32, 32, 0.5, None, 0),
            (200, 200, 230, 230, 0.95, None, 0),
        ]

        result = tracker.assign(detections)

        self.assertEqual(result[0][:4], (12, 12, 32, 32))
        self.assertEqual(result[0][5], 1)

    def test_reset_clears_previous_state(self):
        tracker = SingleSubjectTracker()
        tracker.assign([(10, 10, 30, 30, 0.9, None, 0)])
        tracker.reset()

        result = tracker.assign([(100, 100, 120, 120, 0.6, None, 0)])

        self.assertEqual(result[0][:4], (100, 100, 120, 120))
        self.assertEqual(result[0][5], 1)

    def test_distance_fallback_when_iou_fails(self):
        """Test that distance-based matching works when IoU matching fails.

        This simulates a scenario where the animal moves significantly between
        frames (e.g., when processing every N frames), but the movement is still
        within a reasonable distance.
        """
        tracker = SingleSubjectTracker(iou_threshold=0.3, max_center_distance=200.0)

        # Initial detection at center (20, 20)
        tracker.assign([(10, 10, 30, 30, 0.9, None, 0)])

        # Animal moved significantly - no IoU overlap, but close in distance
        # New detection at center (100, 100) - distance ~113 pixels (within 200)
        # Far detection at center (500, 500) with higher confidence
        detections = [
            (90, 90, 110, 110, 0.5, None, 0),  # Close by distance (center: 100, 100)
            (490, 490, 510, 510, 0.95, None, 0),  # Far away, but higher confidence
        ]

        result = tracker.assign(detections)

        # Should select the close detection by distance, not the high-confidence far one
        self.assertEqual(result[0][:4], (90, 90, 110, 110))
        self.assertEqual(result[0][5], 1)  # Stable track_id

    def test_confidence_fallback_when_distance_exceeds_threshold(self):
        """Test that highest confidence is used when both IoU and distance fail."""
        tracker = SingleSubjectTracker(iou_threshold=0.3, max_center_distance=50.0)

        # Initial detection at center (20, 20)
        tracker.assign([(10, 10, 30, 30, 0.9, None, 0)])

        # All detections are far away (beyond max_center_distance)
        detections = [
            (200, 200, 220, 220, 0.6, None, 0),  # Distance ~255 pixels
            (300, 300, 320, 320, 0.95, None, 0),  # Distance ~400 pixels, but higher confidence
        ]

        result = tracker.assign(detections)

        # Should select highest confidence since both IoU and distance fail
        self.assertEqual(result[0][:4], (300, 300, 320, 320))
        self.assertEqual(result[0][5], 1)

    def test_maintains_stable_track_id_across_large_movements(self):
        """Test that track_id=1 is maintained even with large inter-frame movements."""
        tracker = SingleSubjectTracker(max_center_distance=300.0)

        # Simulate a fish moving across the frame over multiple frames
        positions = [
            (100, 100, 130, 130, 0.9, None, 0),  # Initial position
            (150, 160, 180, 190, 0.85, None, 0),  # Moved ~70 pixels
            (220, 200, 250, 230, 0.88, None, 0),  # Moved ~80 pixels
            (350, 300, 380, 330, 0.9, None, 0),  # Moved ~160 pixels (large move)
        ]

        for i, det in enumerate(positions):
            result = tracker.assign([det])
            self.assertEqual(
                result[0][5], 1, f"Frame {i}: track_id should be 1 but got {result[0][5]}"
            )


if __name__ == "__main__":
    unittest.main()
