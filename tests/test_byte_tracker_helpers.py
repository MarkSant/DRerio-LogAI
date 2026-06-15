"""Unit tests for the pure helpers in ``zebtrack.tracker.byte_tracker``.

The ``BYTETracker.update`` orchestration is already covered by
``test_byte_tracker_single_animal.py`` and the threading-stress suite. This file
pins the *pure-logic* surface that was untested in isolation:

* ``STrack`` coordinate conversions (tlwh/tlbr/xyah), including the ``h <= 0``
  degenerate-box branch,
* the module-level set helpers ``joint_stracks`` / ``sub_stracks`` /
  ``remove_duplicate_stracks``.

These use real ``STrack`` instances — no mocking.
"""

import numpy as np
import pytest

from zebtrack.tracker.basetrack import BaseTrack
from zebtrack.tracker.byte_tracker import (
    STrack,
    joint_stracks,
    remove_duplicate_stracks,
    sub_stracks,
)


@pytest.fixture(autouse=True)
def reset_track_counter():
    BaseTrack.reset_id_counter()
    yield
    BaseTrack.reset_id_counter()


def _strack(tlwh, track_id, score=0.9, start_frame=0, frame_id=0):
    t = STrack(tlwh, score)
    t.track_id = track_id
    t.start_frame = start_frame
    t.frame_id = frame_id
    return t


class TestCoordinateConversions:
    def test_tlwh_to_xyah_golden(self):
        out = STrack.tlwh_to_xyah([10.0, 20.0, 30.0, 40.0])
        # center = (10+15, 20+20) = (25, 40); aspect = 30/40 = 0.75; h = 40.
        np.testing.assert_allclose(out, [25.0, 40.0, 0.75, 40.0])

    def test_tlwh_to_xyah_zero_height_uses_unit_aspect(self):
        out = STrack.tlwh_to_xyah([10.0, 20.0, 30.0, 0.0])
        # h <= 0 → aspect forced to 1.0 (avoids divide-by-zero).
        np.testing.assert_allclose(out, [25.0, 20.0, 1.0, 0.0])

    def test_tlbr_to_tlwh_golden(self):
        np.testing.assert_allclose(STrack.tlbr_to_tlwh([10, 20, 40, 60]), [10, 20, 30, 40])

    def test_tlwh_to_tlbr_golden(self):
        np.testing.assert_allclose(STrack.tlwh_to_tlbr([10, 20, 30, 40]), [10, 20, 40, 60])

    def test_tlbr_tlwh_round_trip(self):
        tlwh = np.array([7.0, 8.0, 30.0, 40.0])
        np.testing.assert_allclose(STrack.tlbr_to_tlwh(STrack.tlwh_to_tlbr(tlwh)), tlwh)

    def test_tlwh_property_when_mean_is_none(self):
        t = STrack([10, 20, 30, 40], 0.9)
        np.testing.assert_allclose(t.tlwh, [10, 20, 30, 40])

    def test_tlbr_property_when_mean_is_none(self):
        t = STrack([10, 20, 30, 40], 0.9)
        np.testing.assert_allclose(t.tlbr, [10, 20, 40, 60])


class TestJointStracks:
    def test_union_dedupes_by_track_id(self):
        a = [_strack([0, 0, 10, 10], track_id=1)]
        b = [_strack([0, 0, 10, 10], track_id=1), _strack([0, 0, 10, 10], track_id=2)]
        res = joint_stracks(a, b)
        assert sorted(t.track_id for t in res) == [1, 2]
        # The id=1 from list a is kept (first-seen wins).
        assert res[0] is a[0]


class TestSubStracks:
    def test_difference_by_track_id(self):
        a = [_strack([0, 0, 10, 10], track_id=1), _strack([0, 0, 10, 10], track_id=2)]
        b = [_strack([0, 0, 10, 10], track_id=2)]
        res = sub_stracks(a, b)
        assert [t.track_id for t in res] == [1]


class TestRemoveDuplicateStracks:
    def test_younger_duplicate_removed(self):
        # Two near-identical boxes → IoU ~1 → duplicate. The track with the
        # shorter lifetime (frame_id - start_frame) is dropped.
        older = _strack([0, 0, 10, 10], track_id=1, start_frame=0, frame_id=50)  # age 50
        younger = _strack([0, 0, 10, 10], track_id=2, start_frame=0, frame_id=5)  # age 5
        resa, resb = remove_duplicate_stracks([older], [younger])
        assert [t.track_id for t in resa] == [1]
        assert resb == []  # younger duplicate removed

    def test_disjoint_boxes_kept(self):
        a = [_strack([0, 0, 10, 10], track_id=1)]
        b = [_strack([100, 100, 110, 110], track_id=2)]
        resa, resb = remove_duplicate_stracks(a, b)
        assert len(resa) == 1 and len(resb) == 1
