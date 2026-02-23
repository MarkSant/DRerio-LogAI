"""Property-based tests for behavioral analysis pure functions.

Tests distance, velocity, and tortuosity invariants using Hypothesis
strategies with minimal ConcreteBehavioralAnalyzer instances.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analyzer(
    xs: list[float],
    ys: list[float],
    fps: float = 30.0,
    pixelcm_x: float = 10.0,
    pixelcm_y: float = 10.0,
) -> ConcreteBehavioralAnalyzer:
    """Build a minimal ConcreteBehavioralAnalyzer from coordinate lists.

    Uses a large square arena to avoid geometry-related issues and
    disables smoothing (window_length=3, polyorder=1) so coordinates
    map intuitively to distance computations.
    """
    n = len(xs)
    timestamps = [i / fps for i in range(n)]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": xs,
            "y_center_px": ys,
            "x1": [x - 5 for x in xs],
            "y1": [y - 5 for y in ys],
            "x2": [x + 5 for x in xs],
            "y2": [y + 5 for y in ys],
        }
    )

    # Large square arena encompassing all points
    arena = [
        [0, 0],
        [10000, 0],
        [10000, 10000],
        [0, 10000],
    ]

    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=pixelcm_x,
        pixelcm_y=pixelcm_y,
        video_height_px=10000,
        arena_polygon_px=arena,
        fps=fps,
        window_length=3,
        polyorder=1,
    )


# Coordinate strategy for points within a reasonable pixel range
_px_coord = st.floats(min_value=100.0, max_value=9000.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Total distance
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestTotalDistanceProperties:
    """Property tests for ConcreteBehavioralAnalyzer.calculate_total_distance."""

    @given(x=_px_coord, y=_px_coord)
    @settings(max_examples=30, database=None)
    def test_stationary_distance_zero(self, x: float, y: float) -> None:
        """A stationary subject (same position for all frames) has distance ~0."""
        analyzer = _make_analyzer(
            xs=[x] * 10,
            ys=[y] * 10,
        )
        dist = analyzer.calculate_total_distance()
        assert dist == pytest.approx(0.0, abs=1e-6)

    @given(
        x1=_px_coord,
        y1=_px_coord,
        x2=_px_coord,
        y2=_px_coord,
    )
    @settings(max_examples=30, database=None)
    def test_distance_non_negative(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        """Total distance is always ≥ 0."""
        analyzer = _make_analyzer(
            xs=[x1, x2],
            ys=[y1, y2],
        )
        dist = analyzer.calculate_total_distance()
        assert dist >= 0.0


# ---------------------------------------------------------------------------
# Velocity
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestVelocityProperties:
    """Property tests for velocity time series."""

    @given(x=_px_coord, y=_px_coord)
    @settings(max_examples=30, database=None)
    def test_stationary_velocity_zero(self, x: float, y: float) -> None:
        """A stationary subject has v_mag ~0 everywhere (except first NaN)."""
        analyzer = _make_analyzer(xs=[x] * 10, ys=[y] * 10)
        vel_df = analyzer.calculate_velocity_timeseries()
        v_mag = vel_df["v_mag"].dropna()
        if not v_mag.empty:
            assert v_mag.max() == pytest.approx(0.0, abs=1e-3)

    @given(
        x1=_px_coord,
        y1=_px_coord,
        x2=_px_coord,
        y2=_px_coord,
    )
    @settings(max_examples=30, database=None)
    def test_vmag_equals_sqrt_vx2_vy2(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        """v_mag == sqrt(vx² + vy²) for all non-NaN rows."""
        analyzer = _make_analyzer(
            xs=[x1, (x1 + x2) / 2, x2],
            ys=[y1, (y1 + y2) / 2, y2],
        )
        vel_df = analyzer.calculate_velocity_timeseries()
        valid = vel_df.dropna(subset=["vx", "vy", "v_mag"])
        if not valid.empty:
            expected = np.sqrt(valid["vx"] ** 2 + valid["vy"] ** 2)
            np.testing.assert_allclose(valid["v_mag"].values, expected.values, rtol=1e-6)

    @given(
        x1=_px_coord,
        y1=_px_coord,
        x2=_px_coord,
        y2=_px_coord,
    )
    @settings(max_examples=30, database=None)
    def test_velocity_non_negative(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        """v_mag is always ≥ 0."""
        analyzer = _make_analyzer(xs=[x1, x2], ys=[y1, y2])
        vel_df = analyzer.calculate_velocity_timeseries()
        v_mag = vel_df["v_mag"].dropna()
        assert (v_mag >= 0).all()


# ---------------------------------------------------------------------------
# Velocity stats
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestVelocityStatsProperties:
    """Property tests for get_velocity_stats."""

    @given(
        x1=_px_coord,
        y1=_px_coord,
        x2=_px_coord,
        y2=_px_coord,
    )
    @settings(max_examples=20, database=None)
    def test_stats_non_negative(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        """Mean, median, std_dev, and max velocities are all ≥ 0."""
        analyzer = _make_analyzer(
            xs=[x1, (x1 + x2) / 2, x2],
            ys=[y1, (y1 + y2) / 2, y2],
        )
        stats = analyzer.get_velocity_stats()
        assert stats["mean"] >= 0.0
        assert stats["median"] >= 0.0
        assert stats["std_dev"] >= 0.0 or np.isnan(stats["std_dev"])
        assert stats["max"] >= 0.0

    @given(
        x1=_px_coord,
        y1=_px_coord,
        x2=_px_coord,
        y2=_px_coord,
    )
    @settings(max_examples=20, database=None)
    def test_max_gte_mean(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        """Maximum velocity is always ≥ mean velocity."""
        analyzer = _make_analyzer(
            xs=[x1, (x1 + x2) / 2, x2],
            ys=[y1, (y1 + y2) / 2, y2],
        )
        stats = analyzer.get_velocity_stats()
        assert stats["max"] >= stats["mean"] - 1e-10


# ---------------------------------------------------------------------------
# Tortuosity
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestTortuosityProperties:
    """Property tests for get_tortuosity."""

    @given(
        x=st.floats(min_value=100.0, max_value=5000.0),
        dx=st.floats(min_value=50.0, max_value=2000.0),
    )
    @settings(max_examples=20, database=None)
    def test_straight_line_tortuosity_near_one(self, x: float, dx: float) -> None:
        """A straight-line path has tortuosity near 1.0.

        With minimal smoothing (window=3, polyorder=1), a straight line
        should yield tortuosity ≈ 1.0. We allow tolerance for edge effects.
        """
        y = 5000.0  # constant y
        xs = [x + i * dx / 9 for i in range(10)]
        ys = [y] * 10

        analyzer = _make_analyzer(xs=xs, ys=ys)
        tortuosity = analyzer.get_tortuosity()

        if not np.isnan(tortuosity):
            assert tortuosity >= 1.0 - 0.05  # allow small floating-point tolerance
