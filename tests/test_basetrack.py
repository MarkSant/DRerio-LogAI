"""Unit tests for ``zebtrack.tracker.basetrack``.

Covers the global track-ID counter, state-transition helpers, the ``end_frame``
property, and the abstract method contract. These are pure-logic tests with no
external dependencies.

``BaseTrack._count`` is **global mutable class state** shared across the whole
process, so every test resets it via the autouse ``reset_track_counter`` fixture
to guarantee order-independence. The need for that reset is itself a documented
footgun of the shared counter.
"""

import pytest

from zebtrack.tracker.basetrack import BaseTrack, TrackState


@pytest.fixture(autouse=True)
def reset_track_counter():
    """Reset the global ID counter before and after each test."""
    BaseTrack.reset_id_counter()
    yield
    BaseTrack.reset_id_counter()


class TestTrackState:
    """The integer values are pinned because they are persisted/compared widely."""

    def test_state_constants(self):
        assert TrackState.New == 0
        assert TrackState.Tracked == 1
        assert TrackState.Lost == 2
        assert TrackState.Removed == 3


class TestIdCounter:
    def test_next_id_is_monotonic(self):
        assert BaseTrack.next_id() == 1
        assert BaseTrack.next_id() == 2
        assert BaseTrack.next_id() == 3

    def test_reset_id_counter(self):
        BaseTrack.next_id()
        BaseTrack.next_id()
        BaseTrack.reset_id_counter()
        assert BaseTrack._count == 0
        assert BaseTrack.next_id() == 1

    def test_set_id_counter(self):
        BaseTrack.set_id_counter(100)
        assert BaseTrack._count == 100
        assert BaseTrack.next_id() == 101

    def test_set_id_counter_zero(self):
        BaseTrack.set_id_counter(0)
        assert BaseTrack.next_id() == 1


class TestStateTransitions:
    def test_mark_lost(self):
        track = BaseTrack()
        track.mark_lost()
        assert track.state == TrackState.Lost

    def test_mark_removed(self):
        track = BaseTrack()
        track.mark_removed()
        assert track.state == TrackState.Removed

    def test_default_state_is_new(self):
        track = BaseTrack()
        assert track.state == TrackState.New


class TestEndFrame:
    def test_end_frame_mirrors_frame_id(self):
        track = BaseTrack()
        track.frame_id = 42
        assert track.end_frame == 42


class TestAbstractContract:
    def test_activate_raises(self):
        with pytest.raises(NotImplementedError):
            BaseTrack().activate()

    def test_predict_raises(self):
        with pytest.raises(NotImplementedError):
            BaseTrack().predict()

    def test_update_raises(self):
        with pytest.raises(NotImplementedError):
            BaseTrack().update()
