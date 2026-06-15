"""Known-answer (golden) unit tests for ``zebtrack.tracker.KalmanFilter``.

The Kalman filter is the core of trajectory smoothing and identity continuity.
Until now it was only exercised indirectly through ``STrack`` with "is not None"
assertions. These tests pin the exact numerical behaviour of every public method
against values computed by hand, with particular attention to the ``dt`` scaling
that the docstring calls "critical for maintaining stable track IDs".

All maths is pure ``numpy`` / ``scipy`` — deterministic, no mocking.
"""

import numpy as np
import pytest

from zebtrack.tracker.kalman_filter import KalmanFilter, chi2inv95


@pytest.fixture
def kf():
    return KalmanFilter(dt=1.0)


class TestModelMatrices:
    def test_motion_matrix_structure_dt1(self, kf):
        # Constant-velocity model: identity with dt on the position/velocity block.
        expected = np.eye(8)
        for i in range(4):
            expected[i, 4 + i] = 1.0
        np.testing.assert_array_equal(kf._motion_mat, expected)

    def test_motion_matrix_scales_with_dt(self):
        kf10 = KalmanFilter(dt=10.0)
        for i in range(4):
            assert kf10._motion_mat[i, 4 + i] == 10.0

    def test_update_matrix_is_eye_4x8(self, kf):
        np.testing.assert_array_equal(kf._update_mat, np.eye(4, 8))

    def test_std_weights_dt1(self, kf):
        assert kf._std_weight_position == pytest.approx(0.05)
        assert kf._std_weight_velocity == pytest.approx(0.0125)

    def test_chi2inv95_table(self):
        # 4 DOF gating threshold used throughout the tracker.
        assert chi2inv95[4] == pytest.approx(9.4877)
        assert chi2inv95[2] == pytest.approx(5.9915)


class TestInitiate:
    def test_mean_layout(self, kf):
        mean, _ = kf.initiate(np.array([10.0, 20.0, 1.0, 40.0]))
        # Position taken from measurement, velocities zero.
        np.testing.assert_array_equal(mean, [10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])

    def test_covariance_is_diagonal_golden(self, kf):
        _, cov = kf.initiate(np.array([10.0, 20.0, 1.0, 40.0]))
        # std = [2*0.05*40, 2*0.05*40, 1e-2, 2*0.05*40,
        #        10*0.0125*40, 10*0.0125*40, 1e-5, 10*0.0125*40]
        #     = [4, 4, 1e-2, 4, 5, 5, 1e-5, 5]
        expected_diag = np.square([4.0, 4.0, 1e-2, 4.0, 5.0, 5.0, 1e-5, 5.0])
        np.testing.assert_allclose(np.diag(cov), expected_diag)
        # Off-diagonal entries must be zero.
        assert np.count_nonzero(cov - np.diag(np.diag(cov))) == 0


class TestPredict:
    def test_constant_velocity_dt1(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 5.0, -3.0, 0.0, 0.0])
        cov = np.eye(8)
        new_mean, _ = kf.predict(mean, cov)
        # x += vx*dt, y += vy*dt, velocities unchanged.
        np.testing.assert_allclose(new_mean[:4], [15.0, 17.0, 1.0, 40.0])
        np.testing.assert_allclose(new_mean[4:], [5.0, -3.0, 0.0, 0.0])

    def test_constant_velocity_dt10_uses_larger_step(self):
        kf10 = KalmanFilter(dt=10.0)
        mean = np.array([10.0, 20.0, 1.0, 40.0, 5.0, -3.0, 0.0, 0.0])
        new_mean, _ = kf10.predict(mean, np.eye(8))
        # dt=10 → 10x larger displacement, the sparse-frame behaviour under test.
        np.testing.assert_allclose(new_mean[:2], [60.0, -10.0])

    def test_covariance_grows(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        _, new_cov = kf.predict(mean, cov)
        # Prediction adds motion noise → uncertainty must not shrink.
        assert np.trace(new_cov) >= np.trace(cov)


class TestProject:
    def test_mean_is_first_four(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 5.0, 6.0, 7.0, 8.0])
        proj_mean, _ = kf.project(mean, np.eye(8))
        np.testing.assert_array_equal(proj_mean, [10.0, 20.0, 1.0, 40.0])

    def test_covariance_adds_innovation(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        _, proj_cov = kf.project(mean, np.eye(8))
        # s = 0.05*40 = 2.0 → s^2 = 4.0; innovation diag = [4, 4, 1e-1^2, 4].
        expected = np.eye(4) + np.diag([4.0, 4.0, 1e-2, 4.0])
        np.testing.assert_allclose(proj_cov, expected)


class TestUpdate:
    def test_zero_innovation_keeps_mean(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        projected_mean, _ = kf.project(mean, cov)
        new_mean, _ = kf.update(mean, cov, projected_mean)
        # Measurement equals prediction → no correction.
        np.testing.assert_allclose(new_mean, mean, atol=1e-9)

    def test_reduces_uncertainty(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8) * 10.0
        _, new_cov = kf.update(mean, cov, np.array([12.0, 22.0, 1.0, 41.0]))
        assert np.trace(new_cov) < np.trace(cov)

    def test_pulls_mean_toward_measurement(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8) * 10.0
        measurement = np.array([20.0, 20.0, 1.0, 40.0])
        new_mean, _ = kf.update(mean, cov, measurement)
        # Corrected x must move toward the measurement (10 -> 20) without overshoot.
        assert 10.0 < new_mean[0] < 20.0


class TestMultiPredict:
    def test_matches_scalar_predict(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 5.0, -3.0, 0.0, 0.0])
        cov = np.eye(8)
        single_mean, single_cov = kf.predict(mean.copy(), cov.copy())

        stacked_mean = np.tile(mean, (3, 1))
        stacked_cov = np.tile(cov, (3, 1, 1))
        multi_mean, multi_cov = kf.multi_predict(stacked_mean, stacked_cov)

        for i in range(3):
            np.testing.assert_allclose(multi_mean[i], single_mean)
            np.testing.assert_allclose(multi_cov[i], single_cov)


class TestGatingDistance:
    def test_gaussian_is_squared_euclidean(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        proj_mean, _ = kf.project(mean, cov)
        measurements = np.array([proj_mean + np.array([3.0, 4.0, 0.0, 0.0])])
        d = kf.gating_distance(mean, cov, measurements, metric="gaussian")
        # 3^2 + 4^2 = 25.
        np.testing.assert_allclose(d, [25.0])

    def test_maha_zero_at_mean(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        proj_mean, _ = kf.project(mean, cov)
        d = kf.gating_distance(mean, cov, np.array([proj_mean]), metric="maha")
        np.testing.assert_allclose(d, [0.0], atol=1e-9)

    def test_only_position_uses_two_dims(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        measurements = np.array([[10.0, 20.0, 999.0, 999.0]])
        # With only_position, aspect/height differences are ignored → distance 0.
        d = kf.gating_distance(mean, cov, measurements, only_position=True, metric="gaussian")
        np.testing.assert_allclose(d, [0.0])

    def test_invalid_metric_raises(self, kf):
        mean = np.array([10.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 0.0])
        cov = np.eye(8)
        with pytest.raises(ValueError, match="invalid distance metric"):
            kf.gating_distance(mean, cov, np.array([[10.0, 20.0, 1.0, 40.0]]), metric="bogus")
