"""Unit tests for the under-covered functions in ``zebtrack.tracker.matching``.

``test_hybrid_matching.py`` already covers ``center_distance``,
``hybrid_iou_center_distance`` and part of ``iou_distance``. This file fills the
remaining gaps: ``linear_assignment`` (notably its ``inf`` handling),
``fuse_score``, ``fuse_iou``, ``merge_matches``, ``embedding_distance`` and the
Kalman gating in ``gate_cost_matrix``.

Duck-typed stand-ins are used for tracks/detections; the Kalman filter is real.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from zebtrack.tracker import matching
from zebtrack.tracker.kalman_filter import KalmanFilter


class TestLinearAssignment:
    def test_empty_matrix(self):
        matches, ua, ub = matching.linear_assignment(np.empty((0, 0)), thresh=0.5)
        assert matches.shape == (0, 2)
        assert ua == () and ub == ()

    def test_identity_optimal(self):
        cost = np.array([[0.1, 0.9], [0.9, 0.1]])
        matches, ua, ub = matching.linear_assignment(cost, thresh=0.5)
        assert {tuple(m) for m in matches} == {(0, 0), (1, 1)}
        assert ua == () and ub == ()

    def test_threshold_filters_all(self):
        cost = np.array([[0.9, 0.9], [0.9, 0.9]])
        matches, ua, ub = matching.linear_assignment(cost, thresh=0.5)
        assert matches.shape == (0, 2)
        assert set(ua) == {0, 1} and set(ub) == {0, 1}

    def test_inf_entries_are_not_matched(self):
        # Row 1 is entirely inf → after the 1e6 substitution it is still far above
        # the threshold and must end up unmatched.
        cost = np.array([[0.1, 0.2], [np.inf, np.inf]])
        matches, ua, ub = matching.linear_assignment(cost, thresh=0.5)
        assert {tuple(m) for m in matches} == {(0, 0)}
        assert set(ua) == {1}
        assert set(ub) == {1}


class TestFuseScore:
    def test_golden(self):
        cost = np.array([[0.2, 0.5]])
        dets = [SimpleNamespace(score=0.8), SimpleNamespace(score=0.6)]
        # iou_sim = 1 - cost = [0.8, 0.5]; fuse_sim = iou_sim*score = [0.64, 0.30];
        # fuse_cost = 1 - fuse_sim.
        out = matching.fuse_score(cost, dets)
        np.testing.assert_allclose(out, [[0.36, 0.70]])

    def test_empty_short_circuit(self):
        empty = np.empty((0, 0))
        assert matching.fuse_score(empty, []).size == 0


class TestFuseIou:
    def test_identical_boxes_full_score(self):
        # Track and detection are the same box with score 1.0 and reid cost 0.
        track = SimpleNamespace(tlbr=np.array([0.0, 0.0, 10.0, 10.0]))
        det = SimpleNamespace(tlbr=np.array([0.0, 0.0, 10.0, 10.0]), score=1.0)
        cost = np.array([[0.0]])
        out = matching.fuse_iou(cost, [track], [det])
        # reid_sim=1, iou_sim=1, score=1 → fuse_sim=1 → fuse_cost=0.
        np.testing.assert_allclose(out, [[0.0]], atol=1e-9)

    def test_output_in_unit_range(self):
        track = SimpleNamespace(tlbr=np.array([0.0, 0.0, 10.0, 10.0]))
        det = SimpleNamespace(tlbr=np.array([5.0, 5.0, 15.0, 15.0]), score=0.5)
        out = matching.fuse_iou(np.array([[0.3]]), [track], [det])
        assert np.all(out >= 0.0) and np.all(out <= 1.0)


class TestMergeMatches:
    def test_consistent_matches_intersect(self):
        m1 = [[0, 0], [1, 1]]
        m2 = [[0, 0], [1, 1]]
        match, up, uq = matching.merge_matches(m1, m2, shape=(2, 2, 2))
        assert set(match) == {(0, 0), (1, 1)}
        assert up == () and uq == ()

    def test_disjoint_matches_have_no_intersection(self):
        match, up, uq = matching.merge_matches([[0, 0]], [[1, 1]], shape=(2, 2, 2))
        assert match == []
        assert set(up) == {0, 1} and set(uq) == {0, 1}


class TestEmbeddingDistance:
    def test_empty(self):
        out = matching.embedding_distance([], [], metric="cosine")
        assert out.shape == (0, 0)

    def test_identical_features_zero_distance(self):
        tracks = [SimpleNamespace(smooth_feat=np.array([1.0, 0.0]))]
        dets = [SimpleNamespace(curr_feat=np.array([1.0, 0.0]))]
        out = matching.embedding_distance(tracks, dets, metric="cosine")
        np.testing.assert_allclose(out, [[0.0]], atol=1e-9)

    def test_orthogonal_features_unit_distance(self):
        tracks = [SimpleNamespace(smooth_feat=np.array([1.0, 0.0]))]
        dets = [SimpleNamespace(curr_feat=np.array([0.0, 1.0]))]
        out = matching.embedding_distance(tracks, dets, metric="cosine")
        np.testing.assert_allclose(out, [[1.0]], atol=1e-9)


class TestGateCostMatrix:
    def _track(self, kf, xyah):
        mean, cov = kf.initiate(np.asarray(xyah, dtype=float))
        return SimpleNamespace(mean=mean, covariance=cov)

    def test_far_detection_is_gated_to_inf(self):
        kf = KalmanFilter(dt=1.0)
        track = self._track(kf, [10, 20, 1.0, 40])
        far_det = SimpleNamespace(to_xyah=lambda: np.array([5000.0, 5000.0, 1.0, 40.0]))
        cost = np.array([[0.5]])
        out = matching.gate_cost_matrix(kf, cost, [track], [far_det])
        assert np.isinf(out[0, 0])

    def test_close_detection_unchanged(self):
        kf = KalmanFilter(dt=1.0)
        track = self._track(kf, [10, 20, 1.0, 40])
        close_det = SimpleNamespace(to_xyah=lambda: np.array([10.0, 20.0, 1.0, 40.0]))
        cost = np.array([[0.5]])
        out = matching.gate_cost_matrix(kf, cost, [track], [close_det])
        assert out[0, 0] == pytest.approx(0.5)

    def test_empty_short_circuit(self):
        kf = KalmanFilter(dt=1.0)
        empty = np.empty((0, 0))
        assert matching.gate_cost_matrix(kf, empty, [], []).size == 0
