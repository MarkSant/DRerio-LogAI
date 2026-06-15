"""Property-based tests for ``zebtrack.tracker.KalmanFilter``.

These verify the mathematical invariants that any correct Kalman filter must
preserve, independent of the specific input:

* covariance matrices stay symmetric,
* covariance matrices stay positive semi-definite (PSD),
* the update (correction) step never increases uncertainty,
* outputs keep their expected shapes.

A violation of any of these would silently corrupt trajectory smoothing.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from zebtrack.tracker.kalman_filter import KalmanFilter


@st.composite
def measurement(draw: st.DrawFn) -> np.ndarray:
    """Generate a plausible (x, y, a, h) bounding-box measurement."""
    x = draw(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
    a = draw(st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False))
    h = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return np.array([x, y, a, h])


def _is_symmetric(cov: np.ndarray) -> bool:
    return np.allclose(cov, cov.T, atol=1e-6)


def _is_psd(cov: np.ndarray) -> bool:
    # Symmetrize to remove tiny numerical asymmetry, then check eigenvalues.
    sym = 0.5 * (cov + cov.T)
    eigvals = np.linalg.eigvalsh(sym)
    return bool(np.all(eigvals >= -1e-6))


@pytest.mark.property
class TestKalmanInvariants:
    @given(m=measurement())
    @settings(max_examples=30, database=None)
    def test_initiate_produces_symmetric_psd_cov(self, m: np.ndarray):
        kf = KalmanFilter(dt=1.0)
        _, cov = kf.initiate(m)
        assert cov.shape == (8, 8)
        assert _is_symmetric(cov)
        assert _is_psd(cov)

    @given(m=measurement())
    @settings(max_examples=30, database=None)
    def test_predict_preserves_symmetry_and_psd(self, m: np.ndarray):
        kf = KalmanFilter(dt=1.0)
        mean, cov = kf.initiate(m)
        new_mean, new_cov = kf.predict(mean, cov)
        assert new_mean.shape == (8,)
        assert new_cov.shape == (8, 8)
        assert _is_symmetric(new_cov)
        assert _is_psd(new_cov)

    @given(m=measurement())
    @settings(max_examples=30, database=None)
    def test_project_preserves_symmetry_and_psd(self, m: np.ndarray):
        kf = KalmanFilter(dt=1.0)
        mean, cov = kf.initiate(m)
        proj_mean, proj_cov = kf.project(mean, cov)
        assert proj_mean.shape == (4,)
        assert proj_cov.shape == (4, 4)
        assert _is_symmetric(proj_cov)
        assert _is_psd(proj_cov)

    @given(m=measurement(), z=measurement())
    @settings(max_examples=30, database=None)
    def test_update_does_not_increase_uncertainty(self, m: np.ndarray, z: np.ndarray):
        kf = KalmanFilter(dt=1.0)
        mean, cov = kf.initiate(m)
        mean, cov = kf.predict(mean, cov)
        trace_before = np.trace(cov)
        _, new_cov = kf.update(mean, cov, z)
        assume(np.all(np.isfinite(new_cov)))
        # A measurement can only sharpen (or, in the limit, preserve) the estimate.
        assert np.trace(new_cov) <= trace_before + 1e-6
        assert _is_symmetric(new_cov)
