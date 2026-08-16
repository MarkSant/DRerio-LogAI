"""
Extended unit tests for SingleSubjectTracker.
"""

from __future__ import annotations

from zebtrack.core.detection.single_subject_tracker import SingleSubjectTracker


class TestSingleSubjectTrackerExtended:
    """Test SingleSubjectTracker tracking strategies and fallbacks."""

    def test_empty_detections_resets_state(self):
        tracker = SingleSubjectTracker(track_id=42)
        # Process detection
        res = tracker.assign([(10, 10, 20, 20, 0.9, None, 0)])
        assert len(res) == 1
        assert res[0][5] == 42  # track_id

        # Empty detection resets
        res_empty = tracker.assign([])
        assert res_empty == []
        assert tracker._last_bbox is None
        assert tracker._last_center is None

    def test_iou_matching_strategy(self):
        tracker = SingleSubjectTracker(track_id=1, iou_threshold=0.3)
        # Frame 1
        tracker.assign([(10, 10, 50, 50, 0.8, None, 0)])

        # Frame 2: slight movement with IoU > 0.3
        # Candidate 1: (12, 12, 52, 52) -> high IoU
        # Candidate 2: (100, 100, 140, 140) -> 0 IoU
        dets = [
            (100, 100, 140, 140, 0.95, None, 0),
            (12, 12, 52, 52, 0.7, None, 0),
        ]
        res = tracker.assign(dets)
        assert len(res) == 1
        # Selected the high IoU candidate despite lower confidence
        assert res[0][0] == 12
        assert res[0][1] == 12

    def test_distance_matching_fallback_strategy(self):
        tracker = SingleSubjectTracker(track_id=1, iou_threshold=0.5, max_center_distance=100.0)
        # Frame 1: center at (30, 30)
        tracker.assign([(10, 10, 50, 50, 0.8, None, 0)])

        # Frame 2: jump to (60, 60, 100, 100) -> 0 IoU, center at (80, 80)
        # Distance = sqrt((80-30)^2 + (80-30)^2) = sqrt(5000) ~ 70.7 < 100
        # Candidate 1: (60, 60, 100, 100), conf 0.6
        # Candidate 2: (500, 500, 540, 540), conf 0.99
        dets = [
            (500, 500, 540, 540, 0.99, None, 0),
            (60, 60, 100, 100, 0.6, None, 0),
        ]
        res = tracker.assign(dets)
        assert len(res) == 1
        # Selected closer distance candidate over far-away high-confidence candidate
        assert res[0][0] == 60
        assert res[0][1] == 60

    def test_confidence_fallback_when_both_fail(self):
        tracker = SingleSubjectTracker(track_id=1, iou_threshold=0.5, max_center_distance=50.0)
        # Frame 1: center at (30, 30)
        tracker.assign([(10, 10, 50, 50, 0.8, None, 0)])

        # Frame 2: both candidates far away (distance > 50)
        dets = [
            (200, 200, 240, 240, 0.4, None, 0),
            (400, 400, 440, 440, 0.9, None, 0),
        ]
        res = tracker.assign(dets)
        assert len(res) == 1
        # Selected highest confidence candidate (400, 400)
        assert res[0][0] == 400
        assert res[0][4] == 0.9

    def test_reset(self):
        tracker = SingleSubjectTracker(track_id=1)
        tracker.assign([(10, 10, 50, 50, 0.8, None, 0)])
        assert tracker._last_bbox is not None

        tracker.reset()
        assert tracker._last_bbox is None
        assert tracker._last_center is None
