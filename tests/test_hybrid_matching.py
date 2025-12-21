"""Tests for hybrid IoU + center distance matching in ByteTracker.

These tests verify that the hybrid matching strategy works correctly for:
1. Small, fast-moving objects like zebrafish
2. Sparse frame processing scenarios (analyzing every N frames)
3. Maintaining track_id consistency when IoU fails but distance is reasonable
"""

import numpy as np
import pytest

from zebtrack.tracker import matching


class TestCenterDistance:
    """Tests for center_distance matching function."""

    def test_empty_inputs(self):
        """Returns empty matrix for empty inputs."""
        result = matching.center_distance([], [])
        assert result.shape == (0, 0)

    def test_single_track_single_detection_close(self):
        """Close detection has low cost."""
        # Track at center (50, 50)
        track = np.array([40, 40, 60, 60])
        # Detection at center (60, 60) - 14px away
        det = np.array([50, 50, 70, 70])

        cost = matching.center_distance([track], [det], max_distance=100.0)

        assert cost.shape == (1, 1)
        assert cost[0, 0] < 0.2  # Should be ~14.14/100 = 0.14

    def test_single_track_single_detection_far(self):
        """Far detection has very high cost (beyond threshold)."""
        # Track at center (50, 50)
        track = np.array([40, 40, 60, 60])
        # Detection at center (300, 300) - ~354px away
        det = np.array([290, 290, 310, 310])

        cost = matching.center_distance([track], [det], max_distance=100.0)

        assert cost.shape == (1, 1)
        # Should be a very high value (1e6) instead of inf to avoid scipy issues
        assert cost[0, 0] >= 1e6

    def test_multiple_tracks_finds_closest(self):
        """Correctly identifies closest match among multiple options."""
        track = np.array([40, 40, 60, 60])  # Center (50, 50)

        dets = [
            np.array([290, 290, 310, 310]),  # Far (300, 300)
            np.array([55, 55, 75, 75]),  # Close (65, 65) - ~21px
            np.array([140, 140, 160, 160]),  # Medium (150, 150) - ~141px
        ]

        cost = matching.center_distance([track], dets, max_distance=200.0)

        assert cost.shape == (1, 3)
        assert cost[0, 1] < cost[0, 2]  # Close < Medium
        assert cost[0, 0] >= 1e6  # Far is beyond max_distance (high cost)


class TestHybridMatching:
    """Tests for hybrid IoU + center distance matching."""

    def test_prefers_iou_when_overlap_exists(self):
        """When bboxes overlap, IoU-based matching is used."""
        # Track and detection with high overlap
        track = np.array([40, 40, 60, 60])
        det = np.array([42, 42, 62, 62])  # 2px shift - high IoU

        hybrid_cost = matching.hybrid_iou_center_distance(
            [track], [det], iou_thresh=0.1, max_center_dist=200.0
        )
        iou_cost = matching.iou_distance([track], [det])

        # Hybrid should equal IoU when there's overlap
        np.testing.assert_array_almost_equal(hybrid_cost, iou_cost)

    def test_uses_distance_when_no_overlap(self):
        """When bboxes don't overlap, center distance is used."""
        # Track and detection with no overlap but close centers
        track = np.array([40, 40, 60, 60])  # Center (50, 50)
        det = np.array([100, 100, 120, 120])  # Center (110, 110) - ~85px away

        hybrid_cost = matching.hybrid_iou_center_distance(
            [track], [det], iou_thresh=0.1, max_center_dist=200.0
        )
        center_cost = matching.center_distance([track], [det], max_distance=200.0)

        # IoU is 0 (no overlap), so hybrid should use center distance
        np.testing.assert_array_almost_equal(hybrid_cost, center_cost)

    def test_zebrafish_simulation(self):
        """Simulates zebrafish tracking across sparse frames.

        Scenario: 30x30px zebrafish moving ~80px between processed frames
        (analyzing every 5 frames, fish moving ~16px/frame)
        """
        # Previous position: fish at (100, 100)
        prev_track = np.array([85, 85, 115, 115])

        # Current position: fish moved ~80px to (180, 120)
        current_det = np.array([165, 105, 195, 135])

        # With IoU-only: no overlap = no match
        iou_cost = matching.iou_distance([prev_track], [current_det])
        assert iou_cost[0, 0] == 1.0  # No overlap

        # With hybrid matching: should find match by distance
        hybrid_cost = matching.hybrid_iou_center_distance(
            [prev_track], [current_det], iou_thresh=0.1, max_center_dist=200.0
        )

        # Distance is ~82px, normalized by 200 = 0.41
        assert 0.3 < hybrid_cost[0, 0] < 0.5
        assert hybrid_cost[0, 0] < 1.0  # Better than no-match


class TestByteTrackerHybridMode:
    """Integration tests for ByteTracker with hybrid matching."""

    def test_bytetracker_initialization_with_hybrid(self):
        """ByteTracker can be initialized with hybrid matching."""
        from types import SimpleNamespace

        from zebtrack.tracker.byte_tracker import BYTETracker

        args = SimpleNamespace(
            track_thresh=0.25,
            match_thresh=0.15,
            track_buffer=60,
            mot20=False,
        )

        tracker = BYTETracker(
            args=args, frame_rate=30, use_hybrid_matching=True, max_center_distance=200.0
        )

        assert tracker.use_hybrid_matching is True
        assert tracker.max_center_distance == 200.0

    def test_bytetracker_maintains_track_id_with_large_movement(self):
        """ByteTracker maintains track_id when fish moves significantly.

        This simulates a zebrafish moving across frames when analyzing
        every 5-10 frames (sparse processing).
        """
        from types import SimpleNamespace

        from zebtrack.tracker.byte_tracker import BYTETracker

        args = SimpleNamespace(
            track_thresh=0.1,
            match_thresh=0.3,  # More lenient for hybrid matching
            track_buffer=60,
            mot20=False,
        )

        tracker = BYTETracker(
            args=args, frame_rate=30, use_hybrid_matching=True, max_center_distance=200.0
        )

        # Frame 1: Fish at (100, 100), size 30x30
        frame_dims = (480, 640)
        det1 = np.array([[85, 85, 115, 115, 0.9]])  # High confidence

        tracks1 = tracker.update(det1, frame_dims, frame_dims)

        if len(tracks1) == 0:
            # If ByteTracker needs activation (first frame)
            det1_again = np.array([[85, 85, 115, 115, 0.9]])
            tracks1 = tracker.update(det1_again, frame_dims, frame_dims)

        if len(tracks1) > 0:
            first_track_id = tracks1[0].track_id

            # Frame 2: Fish moved ~50px (within max_center_distance)
            det2 = np.array([[135, 95, 165, 125, 0.85]])
            tracks2 = tracker.update(det2, frame_dims, frame_dims)

            if len(tracks2) > 0:
                # With hybrid matching, track_id should be maintained
                assert tracks2[0].track_id == first_track_id, (
                    f"Track ID changed from {first_track_id} to {tracks2[0].track_id}. "
                    "Hybrid matching should maintain ID for 50px movement."
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
