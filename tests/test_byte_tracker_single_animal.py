import pytest
import numpy as np
from types import SimpleNamespace
from zebtrack.tracker.byte_tracker import BYTETracker, STrack

class TestByteTrackerSingleAnimal:
    """Test suite for the Single Animal Mode in ByteTracker."""

    @pytest.fixture
    def tracker_args(self):
        return SimpleNamespace(
            track_thresh=0.5,
            match_thresh=0.8,
            track_buffer=30,
            mot20=False,
        )

    def test_immediate_activation(self, tracker_args):
        """Test that new tracks are immediately activated in single animal mode."""
        tracker = BYTETracker(
            args=tracker_args,
            frame_rate=30,
            single_animal_mode=True
        )

        # Create a detection
        # format: x1, y1, x2, y2, score
        detections = np.array([[100, 100, 150, 150, 0.9]], dtype=np.float64)
        img_info = (1000, 1000)
        img_size = (1000, 1000)

        # First update
        tracks = tracker.update(detections, img_info, img_size)

        assert len(tracks) == 1
        assert tracks[0].is_activated
        assert tracks[0].track_id == 1

    def test_id_resurrection(self, tracker_args):
        """Test that a lost track is resurrected instead of creating a new ID."""
        tracker = BYTETracker(
            args=tracker_args,
            frame_rate=30,
            single_animal_mode=True
        )
        img_info = (1000, 1000)
        img_size = (1000, 1000)

        # Frame 1: Initial detection
        det1 = np.array([[100, 100, 150, 150, 0.9]], dtype=np.float64)
        tracks1 = tracker.update(det1, img_info, img_size)
        assert len(tracks1) == 1
        original_id = tracks1[0].track_id

        # Frame 2-10: No detections (Track becomes Lost)
        empty_det = np.empty((0, 5), dtype=np.float64)
        for _ in range(10):
            tracker.update(empty_det, img_info, img_size)
        
        # Verify track is lost
        assert len(tracker.tracked_stracks) == 0
        assert len(tracker.lost_stracks) == 1
        assert tracker.lost_stracks[0].track_id == original_id

        # Frame 11: Reappearance far away (Teleportation)
        # Standard ByteTrack would likely create a new ID due to distance
        det2 = np.array([[800, 800, 850, 850, 0.9]], dtype=np.float64)
        tracks2 = tracker.update(det2, img_info, img_size)

        # Verify ID Persistence
        assert len(tracks2) == 1
        assert tracks2[0].track_id == original_id, f"Expected ID {original_id}, got {tracks2[0].track_id}"
        assert tracks2[0].state == 1 # TrackState.Tracked

    def test_normal_mode_behavior(self, tracker_args):
        """Verify that normal mode still behaves as expected (no resurrection)."""
        tracker = BYTETracker(
            args=tracker_args,
            frame_rate=30,
            single_animal_mode=False
        )
        img_info = (1000, 1000)
        img_size = (1000, 1000)

        # Frame 1
        det1 = np.array([[100, 100, 150, 150, 0.9]], dtype=np.float64)
        tracks1 = tracker.update(det1, img_info, img_size)
        id1 = tracks1[0].track_id

        # Lose it
        empty_det = np.empty((0, 5), dtype=np.float64)
        for _ in range(5):
            tracker.update(empty_det, img_info, img_size)

        # Reappear far away - should be new ID in normal mode (due to high cost)
        det2 = np.array([[900, 900, 950, 950, 0.9]], dtype=np.float64)
        tracks2 = tracker.update(det2, img_info, img_size)

        # Note: Whether it creates a new ID depends on match threshold and cost.
        # With 800px jump, it should be a new ID or at least not forced resurrection.
        # If it matches by chance, this test might be flaky, but the key is logic difference.
        
        # In normal mode, if it fails matching, it creates new track with NEW ID
        # The new track starts as Unconfirmed (since frame_id > 1)
        # So tracks2 might be empty if it's unconfirmed!
        
        if len(tracks2) > 0:
            assert tracks2[0].track_id != id1
        else:
            # It's unconfirmed, so it's not returned. This proves behavior difference.
            pass
