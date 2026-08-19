"""Extended unit tests for TrackState and BaseTrack in tracker/basetrack.py."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.tracker.basetrack import BaseTrack, TrackState


class ConcreteTrack(BaseTrack):
    """Concrete implementation of BaseTrack for testing."""

    def activate(self, *args):
        self.is_activated = True
        self.state = TrackState.Tracked

    def predict(self):
        pass

    def update(self, *args, **kwargs):
        pass


class TestBaseTrack:
    """Test BaseTrack id counters, state transitions, and abstract methods."""

    def test_initial_state_defaults(self):
        track = ConcreteTrack()
        assert track.track_id == 0
        assert track.is_activated is False
        assert track.state == TrackState.New
        assert track.score == 0
        assert track.start_frame == 0
        assert track.frame_id == 0
        assert track.time_since_update == 0
        assert track.end_frame == 0
        assert track.location == (np.inf, np.inf)

    def test_id_counter_lifecycle(self):
        BaseTrack.reset_id_counter()
        id1 = BaseTrack.next_id()
        id2 = BaseTrack.next_id()
        assert id1 == 1
        assert id2 == 2

        BaseTrack.set_id_counter(100)
        assert BaseTrack.next_id() == 101

        BaseTrack.reset_id_counter()
        assert BaseTrack.next_id() == 1

    def test_mark_lost_and_removed(self):
        track = ConcreteTrack()
        track.mark_lost()
        assert track.state == TrackState.Lost

        track.mark_removed()
        assert track.state == TrackState.Removed

    def test_abstract_methods_raise_not_implemented(self):
        raw_track = BaseTrack()

        with pytest.raises(NotImplementedError):
            raw_track.activate()

        with pytest.raises(NotImplementedError):
            raw_track.predict()

        with pytest.raises(NotImplementedError):
            raw_track.update()

    def test_concrete_track_activate(self):
        track = ConcreteTrack()
        track.activate()
        assert track.is_activated is True
        assert track.state == TrackState.Tracked
