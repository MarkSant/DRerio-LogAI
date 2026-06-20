"""Property-based tests for *physical invariants* of behavioural metrics.

``tests/test_property_behavior.py`` already pins the basic invariants
(distance/velocity non-negativity, ``v_mag`` formula, tortuosity >= 1, ...).
This module adds the invariants that protect the **numbers that reach a paper**
from silent unit/geometry regressions:

* unit consistency -- a cm distance scales as ``1 / pixelcm`` (px<->cm);
* spatial scale-invariance of the (dimensionless) tortuosity ratio;
* translation invariance of distance and tortuosity;
* distance conservation under resampling a straight path;
* the freezing *fraction* stays inside ``[0, 1]``.

All analyzers are built with ``window_length=1, polyorder=0`` so Savitzky-Golay
smoothing is bypassed (see ``BehavioralAnalyzer._preprocess_data``) and the
metric maths is exercised on the raw geometry -- smoothing itself is covered by
the existing behaviour tests.

Style mirrors ``tests/test_property_zone_scaler.py`` (``.map``-based strategies,
``database=None``, ``@pytest.mark.property``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

# Arena polygon is required by the constructor, but the metrics under test
# (distance, velocity, tortuosity, freezing) depend only on the trajectory
# coordinates -- not on arena containment -- so its exact size is irrelevant here.
_ARENA_PX = [[0, 0], [20000, 0], [20000, 20000], [0, 20000]]


def _make_analyzer(
    xs: list[float],
    ys: list[float],
    *,
    fps: float = 30.0,
    pixelcm_x: float = 10.0,
    pixelcm_y: float = 10.0,
) -> ConcreteBehavioralAnalyzer:
    """Build an un-smoothed analyzer (window=1, polyorder=0) from coord lists."""
    n = len(xs)
    df = pd.DataFrame(
        {
            "timestamp": [i / fps for i in range(n)],
            "x_center_px": xs,
            "y_center_px": ys,
            "x1": [x - 5 for x in xs],
            "y1": [y - 5 for y in ys],
            "x2": [x + 5 for x in xs],
            "y2": [y + 5 for y in ys],
        }
    )
    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=pixelcm_x,
        pixelcm_y=pixelcm_y,
        video_height_px=20000,
        arena_polygon_px=_ARENA_PX,
        fps=fps,
        window_length=1,
        polyorder=0,
    )


# Coordinates comfortably inside the arena.
_coord = st.floats(min_value=500.0, max_value=18000.0, allow_nan=False, allow_infinity=False)
# Strictly-positive, finite px/cm scales.
_pixelcm = st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False)


def _path_points(draw_list: list[float]) -> tuple[list[float], list[float]]:
    """Split a flat list of draws into interleaved (xs, ys)."""
    xs = draw_list[0::2]
    ys = draw_list[1::2]
    return xs, ys


@pytest.mark.property
class TestUnitConsistency:
    """``px -> cm`` conversion: a cm distance scales as ``1 / pixelcm``."""

    @given(
        xs=st.lists(_coord, min_size=3, max_size=8),
        ys=st.lists(_coord, min_size=3, max_size=8),
        p1=_pixelcm,
        p2=_pixelcm,
    )
    @settings(max_examples=40, database=None)
    def test_distance_scales_inverse_with_pixelcm(
        self, xs: list[float], ys: list[float], p1: float, p2: float
    ) -> None:
        n = min(len(xs), len(ys))
        xs, ys = xs[:n], ys[:n]
        d1 = _make_analyzer(xs, ys, pixelcm_x=p1, pixelcm_y=p1).calculate_total_distance()
        d2 = _make_analyzer(xs, ys, pixelcm_x=p2, pixelcm_y=p2).calculate_total_distance()
        # distance ~ pixel_path / pixelcm  =>  distance * pixelcm is the invariant.
        assert d1 * p1 == pytest.approx(d2 * p2, rel=1e-6, abs=1e-9)


@pytest.mark.property
class TestTranslationInvariance:
    """Shifting every coordinate by a constant leaves geometric metrics fixed."""

    @given(
        xs=st.lists(_coord, min_size=4, max_size=10),
        ys=st.lists(_coord, min_size=4, max_size=10),
        shift=st.floats(min_value=-400.0, max_value=400.0),
    )
    @settings(max_examples=40, database=None)
    def test_distance_translation_invariant(
        self, xs: list[float], ys: list[float], shift: float
    ) -> None:
        n = min(len(xs), len(ys))
        xs, ys = xs[:n], ys[:n]
        base = _make_analyzer(xs, ys).calculate_total_distance()
        shifted = _make_analyzer(
            [x + shift for x in xs], [y + shift for y in ys]
        ).calculate_total_distance()
        assert base == pytest.approx(shifted, rel=1e-6, abs=1e-6)


@pytest.mark.property
class TestScaleInvarianceOfTortuosity:
    """Tortuosity is a dimensionless ratio: invariant under uniform scaling."""

    @given(
        flat=st.lists(_coord, min_size=8, max_size=20),
        k=st.floats(min_value=0.1, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=40, database=None)
    def test_tortuosity_uniform_scale_invariant(self, flat: list[float], k: float) -> None:
        xs, ys = _path_points(flat)
        n = min(len(xs), len(ys))
        xs, ys = xs[:n], ys[:n]
        # Scale about the centroid. Tortuosity does not depend on arena
        # containment, so scaled points may fall outside the arena without
        # affecting the ratio under test.
        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        sx = [cx + (x - cx) * k for x in xs]
        sy = [cy + (y - cy) * k for y in ys]

        base = _make_analyzer(xs, ys).get_tortuosity()
        scaled = _make_analyzer(sx, sy).get_tortuosity()
        # get_tortuosity returns NaN when the net displacement is 0 while the
        # path length is > 0 (e.g. a closed loop); scaling preserves that case.
        if np.isnan(base) or np.isnan(scaled):
            assert np.isnan(base) and np.isnan(scaled)
        else:
            assert base == pytest.approx(scaled, rel=1e-6, abs=1e-6)
            assert base >= 1.0 - 1e-9


@pytest.mark.property
class TestDistanceConservationUnderResampling:
    """Sampling a straight path more densely does not change its length."""

    @given(
        x0=_coord,
        y0=_coord,
        dx=st.floats(min_value=-5000.0, max_value=5000.0),
        dy=st.floats(min_value=-5000.0, max_value=5000.0),
        n=st.integers(min_value=3, max_value=12),
    )
    @settings(max_examples=40, database=None)
    def test_straight_path_length_independent_of_sampling(
        self, x0: float, y0: float, dx: float, dy: float, n: int
    ) -> None:
        # Keep the endpoint inside the arena.
        x1 = float(np.clip(x0 + dx, 500.0, 18000.0))
        y1 = float(np.clip(y0 + dy, 500.0, 18000.0))

        coarse_x = list(np.linspace(x0, x1, n))
        coarse_y = list(np.linspace(y0, y1, n))
        fine_x = list(np.linspace(x0, x1, 2 * n - 1))
        fine_y = list(np.linspace(y0, y1, 2 * n - 1))

        d_coarse = _make_analyzer(coarse_x, coarse_y).calculate_total_distance()
        d_fine = _make_analyzer(fine_x, fine_y).calculate_total_distance()
        assert d_coarse == pytest.approx(d_fine, rel=1e-6, abs=1e-6)


@pytest.mark.property
class TestFreezingFractionBounds:
    """The freezing *fraction* of the session is always within ``[0, 1]``."""

    @given(
        flat=st.lists(_coord, min_size=20, max_size=60),
        vel_threshold=st.floats(min_value=0.0, max_value=500.0),
    )
    @settings(max_examples=30, database=None)
    def test_freezing_fraction_in_unit_interval(
        self, flat: list[float], vel_threshold: float
    ) -> None:
        xs, ys = _path_points(flat)
        n = min(len(xs), len(ys))
        xs, ys = xs[:n], ys[:n]
        analyzer = _make_analyzer(xs, ys, fps=30.0)

        episodes = analyzer.detect_freezing_episodes(min_duration=0.0, vel_threshold=vel_threshold)
        total_freezing = sum(ep["duration"] for ep in episodes)

        index = analyzer.trajectory_data.index
        total_time = (index[-1] - index[0]).total_seconds()

        if total_time > 0:
            fraction = total_freezing / total_time
            assert -1e-9 <= fraction <= 1.0 + 1e-9
