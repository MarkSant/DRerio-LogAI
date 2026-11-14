from types import SimpleNamespace

import numpy as np
import pytest

from zebtrack.tracker.byte_tracker import BYTETracker


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
        tracker = BYTETracker(args=tracker_args, frame_rate=30, single_animal_mode=True)

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
        tracker = BYTETracker(args=tracker_args, frame_rate=30, single_animal_mode=True)
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
        assert tracks2[0].track_id == original_id, (
            f"Expected ID {original_id}, got {tracks2[0].track_id}"
        )
        assert tracks2[0].state == 1  # TrackState.Tracked

    def test_normal_mode_behavior(self, tracker_args):
        """Verify that normal mode still behaves as expected (no resurrection)."""
        tracker = BYTETracker(args=tracker_args, frame_rate=30, single_animal_mode=False)
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


class TestLostTrackLifecycle:
    """Lost-pool bookkeeping (issue #630), multi-subject mode.

    Before the fix a re-found track stayed in both ``tracked_stracks`` and
    ``lost_stracks``; ``remove_duplicate_stracks`` then dropped it from the
    tracked side and the tracker never emitted that animal again. Expired
    tracks also stayed in the matching pool, so ``max_time_lost`` had no effect.
    """

    BOX = np.array([[100.0, 100.0, 140.0, 140.0, 0.95]])
    EMPTY = np.empty((0, 5))
    SIZE = (480, 640)

    @pytest.fixture(autouse=True)
    def _fresh_ids(self):
        from zebtrack.tracker.basetrack import BaseTrack

        BaseTrack.reset_id_counter()

    def _tracker(self) -> BYTETracker:
        args = SimpleNamespace(track_thresh=0.5, match_thresh=0.8, track_buffer=30, mot20=False)
        # frame_rate=10 -> buffer of 10 frames (1 s, the configured 30 @ 30 fps).
        return BYTETracker(args=args, frame_rate=10)

    def _confirmed(self) -> tuple[BYTETracker, int]:
        tracker = self._tracker()
        for _ in range(3):
            out = tracker.update(self.BOX, self.SIZE, self.SIZE)
        return tracker, out[0].track_id

    def test_a_track_refound_within_the_buffer_keeps_its_id_and_is_emitted(self):
        tracker, original_id = self._confirmed()
        for _ in range(3):
            tracker.update(self.EMPTY, self.SIZE, self.SIZE)

        out = tracker.update(self.BOX, self.SIZE, self.SIZE)

        assert [t.track_id for t in out] == [original_id]
        assert tracker.lost_stracks == []

    def test_an_expired_track_leaves_the_pool_and_the_animal_gets_a_new_id(self):
        tracker, original_id = self._confirmed()
        removed_at = None
        for gap in range(1, 30):
            tracker.update(self.EMPTY, self.SIZE, self.SIZE)
            if tracker.removed_stracks:
                removed_at = gap
                break

        # end_frame is the last hit; removal on the first frame PAST the limit.
        assert removed_at == tracker.max_time_lost + 1
        assert tracker.lost_stracks == []

        tracker.update(self.BOX, self.SIZE, self.SIZE)  # new, unconfirmed
        out = tracker.update(self.BOX, self.SIZE, self.SIZE)

        assert len(out) == 1
        assert out[0].track_id != original_id

    def test_removed_tracks_do_not_accumulate(self):
        tracker, _ = self._confirmed()
        for _ in range(40):
            tracker.update(self.EMPTY, self.SIZE, self.SIZE)

        assert tracker.removed_stracks == []
        assert tracker.lost_stracks == []


class TestLostTrackAge:
    """How long a lost track survives, in REAL seconds (issue #654).

    ``track_buffer`` is a number of frames at the 30 fps reference, so
    ``track_buffer=30`` means 1 s. Before #654 the update count was scaled by
    ``processing_interval`` while each ``update()`` already spanned that many
    frames: the interval entered twice (``track_buffer * interval**2 / 30`` s).
    """

    BOX = np.array([[100.0, 100.0, 140.0, 140.0, 0.95]])
    EMPTY = np.empty((0, 5))
    SIZE = (480, 640)

    @pytest.fixture(autouse=True)
    def _fresh_ids(self):
        from zebtrack.tracker.basetrack import BaseTrack

        BaseTrack.reset_id_counter()

    @staticmethod
    def _tracker(*, frame_rate=30, interval=1, track_buffer=30, single=False) -> BYTETracker:
        args = SimpleNamespace(
            track_thresh=0.5, match_thresh=0.8, track_buffer=track_buffer, mot20=False
        )
        return BYTETracker(
            args=args,
            frame_rate=frame_rate,
            processing_interval=interval,
            single_animal_mode=single,
        )

    def _updates_until_removed(self, tracker, *, period_s=None, limit=10_000):
        """Confirm one track, then feed empty updates; return (updates, seconds) to removal.

        With ``period_s`` every update carries its instant (``frame_time_s``);
        without it the tracker has to fall back to counting updates.
        """
        clock = 0.0

        def stamp():
            return None if period_s is None else clock

        for _ in range(3):
            tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=stamp())
            clock += period_s or 0.0
        last_seen = clock - (period_s or 0.0)
        for updates in range(1, limit):
            tracker.update(self.EMPTY, self.SIZE, self.SIZE, frame_time_s=stamp())
            if tracker.removed_stracks:
                return updates, clock - last_seen
            clock += period_s or 0.0
        raise AssertionError("the lost track was never removed")

    def test_sparse_detection_without_clock_does_not_square_the_interval(self):
        # interval=10 at 30 fps: one update every 1/3 s. 1 s of buffer = 3 updates.
        tracker = self._tracker(frame_rate=30, interval=10, track_buffer=30)

        updates, _ = self._updates_until_removed(tracker)

        assert tracker.max_time_lost == 3
        assert updates == tracker.max_time_lost + 1
        real_seconds = updates * 10 / 30
        # One update of slack: removal is on the first update PAST the limit.
        assert real_seconds <= 1.0 + 10 / 30

    def test_with_a_clock_the_buffer_is_the_configured_seconds_whatever_the_cadence(self):
        # 30 fps capture, 1 frame in 2 analysed: the tracker sees 15 updates/s
        # but still believes the source runs at 30 fps.
        tracker = self._tracker(frame_rate=30, interval=1, track_buffer=30)

        updates, seconds = self._updates_until_removed(tracker, period_s=1 / 15)

        assert seconds == pytest.approx(1.0, abs=1 / 15 + 1e-9)
        assert updates < 30  # counting updates would have kept it 2 s

    def test_with_a_clock_a_gap_without_updates_still_ages_the_track(self):
        # Nothing called update() for 5 s (frames dropped, aquarium empty): the
        # next update must not re-find a track that expired in between.
        tracker = self._tracker(frame_rate=30, interval=1, track_buffer=30)
        for i in range(3):
            out = tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=i / 30)
        original_id = out[0].track_id
        tracker.update(self.EMPTY, self.SIZE, self.SIZE, frame_time_s=3 / 30)

        tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=5.0)
        out = tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=5.0 + 1 / 30)

        assert [t.track_id for t in out] != [original_id]
        assert all(t.track_id != original_id for t in tracker.lost_stracks)

    def test_with_a_clock_a_track_refound_within_the_buffer_keeps_its_id(self):
        tracker = self._tracker(frame_rate=30, interval=1, track_buffer=30)
        for i in range(3):
            out = tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=i / 30)
        original_id = out[0].track_id
        tracker.update(self.EMPTY, self.SIZE, self.SIZE, frame_time_s=3 / 30)

        out = tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=0.9)

        assert [t.track_id for t in out] == [original_id]

    def test_single_animal_mode_keeps_the_track_six_buffers_by_clock_and_by_count(self):
        from zebtrack.tracker.byte_tracker import SINGLE_ANIMAL_LOST_FACTOR

        assert SINGLE_ANIMAL_LOST_FACTOR == 6
        timed = self._tracker(frame_rate=30, interval=1, track_buffer=30, single=True)
        _, seconds = self._updates_until_removed(timed, period_s=1 / 15)
        assert seconds == pytest.approx(6.0, abs=1 / 15 + 1e-9)

        counted = self._tracker(frame_rate=10, interval=1, track_buffer=30, single=True)
        updates, _ = self._updates_until_removed(counted)
        # 10 updates (1 s at 10 fps) x 6, removed on the first update past it.
        assert updates == 61

    def test_a_clock_that_stands_still_falls_back_to_counting(self):
        # A backend whose CAP_PROP_POS_MSEC is always 0: trusting it would keep
        # every age at 0 s and the lost track alive forever.
        tracker = self._tracker(frame_rate=30, interval=1, track_buffer=30)
        for _ in range(3):
            tracker.update(self.BOX.copy(), self.SIZE, self.SIZE, frame_time_s=0.0)
        removed_after = None
        for n in range(1, 200):
            tracker.update(self.EMPTY, self.SIZE, self.SIZE, frame_time_s=0.0)
            if tracker.removed_stracks:
                removed_after = n
                break

        assert removed_after == tracker.max_time_lost + 1
