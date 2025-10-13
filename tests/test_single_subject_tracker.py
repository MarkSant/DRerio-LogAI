import unittest

from zebtrack.core.single_subject_tracker import SingleSubjectTracker


class TestSingleSubjectTracker(unittest.TestCase):
    def test_selects_highest_confidence_initial(self):
        tracker = SingleSubjectTracker()
        detections = [
            (0, 0, 10, 10, 0.3, None),
            (5, 5, 20, 20, 0.8, None),
        ]

        result = tracker.assign(detections)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][:4], (5, 5, 20, 20))
        self.assertEqual(result[0][5], 1)

    def test_prefers_high_iou_over_confidence(self):
        tracker = SingleSubjectTracker()
        tracker.assign([(10, 10, 30, 30, 0.9, None)])

        detections = [
            (12, 12, 32, 32, 0.5, None),
            (200, 200, 230, 230, 0.95, None),
        ]

        result = tracker.assign(detections)

        self.assertEqual(result[0][:4], (12, 12, 32, 32))
        self.assertEqual(result[0][5], 1)

    def test_reset_clears_previous_state(self):
        tracker = SingleSubjectTracker()
        tracker.assign([(10, 10, 30, 30, 0.9, None)])
        tracker.reset()

        result = tracker.assign([(100, 100, 120, 120, 0.6, None)])

        self.assertEqual(result[0][:4], (100, 100, 120, 120))
        self.assertEqual(result[0][5], 1)


if __name__ == "__main__":
    unittest.main()
