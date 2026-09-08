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


class TestBboxIous:
    """Locks the arithmetic inherited from ``cython_bbox.bbox_overlaps``.

    Every number below was produced by ``cython_bbox`` 0.1.5 itself, before the
    dependency was dropped. It shipped as a source distribution only, so
    installing the project required a C toolchain; the replacement is pure
    NumPy and must stay numerically indistinguishable from it.
    """

    def test_identical_boxes_score_one(self):
        box = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert matching.bbox_ious(box, box)[0, 0] == pytest.approx(1.0)

    def test_disjoint_boxes_score_zero(self):
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[100.0, 100.0, 110.0, 110.0]])
        assert matching.bbox_ious(a, b)[0, 0] == 0.0

    def test_partial_overlap_keeps_the_inclusive_pixel_convention(self):
        """The discriminating case: 36/206, not 25/175.

        ``cython_bbox`` counts a box's final pixel, so ``[0, 0, 10, 10]`` is
        11 px wide. Computing the same overlap without that convention yields
        0.1428..., and nothing would fail -- the tracker would just match
        different boxes and write different track identities.
        """
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[5.0, 5.0, 15.0, 15.0]])
        assert matching.bbox_ious(a, b)[0, 0] == pytest.approx(0.17475728155339806, abs=1e-15)

    def test_matrix_matches_cython_bbox_reference(self):
        a = np.array([[0.0, 0.0, 10.0, 10.0], [20.0, 20.0, 30.0, 30.0], [5.0, 5.0, 25.0, 25.0]])
        b = np.array([[0.0, 0.0, 10.0, 10.0], [5.0, 5.0, 15.0, 15.0], [100.0, 100.0, 110.0, 110.0]])
        expected = np.array(
            [
                [1.0, 0.17475728155339806, 0.0],
                [0.0, 0.0, 0.0],
                [0.06844106463878327, 0.2743764172335601, 0.0],
            ]
        )
        np.testing.assert_allclose(matching.bbox_ious(a, b), expected, atol=1e-15)

    @pytest.mark.parametrize(
        ("n_a", "n_b"),
        [(0, 3), (3, 0), (0, 0)],
    )
    def test_empty_inputs_return_correctly_shaped_zeros(self, n_a, n_b):
        a = np.zeros((n_a, 4))
        b = np.zeros((n_b, 4))
        out = matching.bbox_ious(a, b)
        assert out.shape == (n_a, n_b)

    def test_never_returns_nan_on_degenerate_boxes(self):
        """A zero union must score 0.0, the way ``cython_bbox`` did.

        A nan would survive into the cost matrix and silently lose the match:
        comparisons against the threshold are false for nan.
        """
        degenerate = np.array([[5.0, 5.0, 4.0, 4.0]])
        out = matching.bbox_ious(degenerate, degenerate)
        assert not np.isnan(out).any()

    def test_ious_wrapper_accepts_lists(self):
        """``ious`` is what the tracker calls, and it is fed plain lists."""
        out = matching.ious([[0, 0, 10, 10]], [[0, 0, 10, 10]])
        assert out[0, 0] == pytest.approx(1.0)
