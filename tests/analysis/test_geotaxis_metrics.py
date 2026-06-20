"""Golden + invariant tests for geotaxis / vertical-zone metrics.

Geotaxis (preference for the bottom of the tank) and the vertical-zone split are
core anxiety read-outs for zebrafish behaviour, yet ``get_geotaxis_timeseries``
and ``get_vertical_zone_timeseries`` had no direct tests (only incidental
coverage via ``calculate_geotaxis_index``). A wrong zone assignment silently
flips an anxiety conclusion in the paper, so we pin the exact maths and the
invariants a consumer relies on.

Pipeline conventions (verified against ``behavior.py``):
    y_cm = (video_height_px - y_center_px) / pixelcm_y      # Y inverted
    distance_to_bottom = max(y_cm - arena_min_y_cm, 0)
    vertical_zone = clip(floor((y_cm - min_y) / zone_height), 0, num_zones - 1)
    # zone 0 == bottom, zone num_zones-1 == top

Analyzers use ``window_length=1, polyorder=0`` so Savitzky-Golay smoothing is
bypassed (fallback identity for window < 3) and the geometry is exact.

For an arena spanning the full frame ``[[0,0],[W,0],[W,H],[0,H]]`` with
``video_height_px = H`` and isotropic ``pixelcm = p``: arena bottom in cm is 0
and arena top is ``H / p``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

_VIDEO_H = 1000
_PIXELCM = 10.0  # arena height in cm = 1000 / 10 = 100 cm
_ARENA_PX = [[0, 0], [_VIDEO_H, 0], [_VIDEO_H, _VIDEO_H], [0, _VIDEO_H]]


def _analyzer(
    ys: list[float],
    *,
    xs: list[float] | None = None,
    fps: float = 30.0,
) -> ConcreteBehavioralAnalyzer:
    """Build an un-smoothed analyzer from a list of vertical pixel positions."""
    n = len(ys)
    if xs is None:
        xs = [500.0] * n
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
        pixelcm_x=_PIXELCM,
        pixelcm_y=_PIXELCM,
        video_height_px=_VIDEO_H,
        arena_polygon_px=_ARENA_PX,
        fps=fps,
        window_length=1,
        polyorder=0,
    )


class TestVerticalZoneGolden:
    """Hand-computed zone assignments (num_zones=4 -> zone_height=25 cm)."""

    @pytest.mark.parametrize(
        ("y_px", "expected_zone"),
        [
            (990, 0),  # y_cm = 1   -> floor(1/25)  = 0 (bottom)
            (510, 1),  # y_cm = 49  -> floor(49/25) = 1
            (260, 2),  # y_cm = 74  -> floor(74/25) = 2
            (10, 3),  # y_cm = 99  -> floor(99/25) = 3 (top)
        ],
    )
    def test_zone_assignment(self, y_px: float, expected_zone: int) -> None:
        zones = _analyzer([y_px] * 4).get_vertical_zone_timeseries(num_zones=4)
        assert (zones == expected_zone).all()

    def test_bottom_is_zone_zero_top_is_max(self) -> None:
        # Bottom of image (large y_px) -> zone 0; top (small y_px) -> zone N-1.
        zones = _analyzer([1000.0, 0.0]).get_vertical_zone_timeseries(num_zones=5)
        assert zones.iloc[0] == 0
        assert zones.iloc[1] == 4


class TestDistanceToBottomGolden:
    """Hand-computed distance-to-bottom values."""

    def test_distance_to_bottom_values(self) -> None:
        # y_px 990 -> y_cm 1 -> dist 1; y_px 10 -> y_cm 99 -> dist 99.
        dist = _analyzer([990.0, 10.0]).get_geotaxis_timeseries()
        assert dist.iloc[0] == pytest.approx(1.0)
        assert dist.iloc[1] == pytest.approx(99.0)

    def test_distance_to_bottom_never_negative(self) -> None:
        # A subject "below" the arena floor clamps to 0, not a negative distance.
        dist = _analyzer([1000.0, 1200.0]).get_geotaxis_timeseries()
        assert (dist >= 0.0).all()


class TestGeotaxisIndexGolden:
    """Hand-computed geotaxis index aggregates."""

    def _half_bottom_half_top(self) -> ConcreteBehavioralAnalyzer:
        # 4 frames at the bottom (y_cm=1) and 4 at the top (y_cm=99).
        return _analyzer([990.0] * 4 + [10.0] * 4)

    def test_average_distance(self) -> None:
        # mean([1,1,1,1,99,99,99,99]) = 50.
        idx = self._half_bottom_half_top().calculate_geotaxis_index(method="average_distance")
        assert idx == pytest.approx(50.0)

    def test_time_near_bottom_percentage(self) -> None:
        # 4 of 8 frames within 10 cm of the bottom -> 50 %.
        idx = self._half_bottom_half_top().calculate_geotaxis_index(
            method="time_near_bottom", distance_threshold=10.0
        )
        assert idx == pytest.approx(50.0)

    def test_zone_time_percentages(self) -> None:
        zones = self._half_bottom_half_top().calculate_geotaxis_index(
            method="zone_time", num_zones=4, bottom_zones=1
        )
        assert isinstance(zones, dict)
        assert zones["zone_0_pct"] == pytest.approx(50.0)
        assert zones["zone_3_pct"] == pytest.approx(50.0)
        assert zones["zone_1_pct"] == pytest.approx(0.0)
        assert zones["zone_2_pct"] == pytest.approx(0.0)
        assert zones["bottom_zones_pct"] == pytest.approx(50.0)


# Vertical pixel positions strictly inside the frame.
_y_px = st.floats(min_value=1.0, max_value=999.0, allow_nan=False, allow_infinity=False)
_num_zones = st.integers(min_value=2, max_value=8)


@pytest.mark.property
class TestVerticalZoneInvariants:
    """Invariants of the vertical-zone classifier."""

    @given(ys=st.lists(_y_px, min_size=1, max_size=30), num_zones=_num_zones)
    @settings(max_examples=50, database=None)
    def test_zone_within_bounds(self, ys: list[float], num_zones: int) -> None:
        zones = _analyzer(ys).get_vertical_zone_timeseries(num_zones=num_zones)
        assert (zones >= 0).all()
        assert (zones <= num_zones - 1).all()

    @given(ya=_y_px, yb=_y_px, num_zones=_num_zones)
    @settings(max_examples=50, database=None)
    def test_monotonic_with_depth(self, ya: float, yb: float, num_zones: int) -> None:
        """Deeper in the tank (larger y_px) never yields a higher zone index."""
        za = _analyzer([ya]).get_vertical_zone_timeseries(num_zones=num_zones).iloc[0]
        zb = _analyzer([yb]).get_vertical_zone_timeseries(num_zones=num_zones).iloc[0]
        if ya >= yb:  # a is deeper (or equal)
            assert za <= zb
        else:
            assert za >= zb


@pytest.mark.property
class TestGeotaxisIndexInvariants:
    """Bounded-range invariants for the geotaxis aggregates."""

    @given(ys=st.lists(_y_px, min_size=2, max_size=30))
    @settings(max_examples=40, database=None)
    def test_distance_non_negative(self, ys: list[float]) -> None:
        assert (_analyzer(ys).get_geotaxis_timeseries() >= 0.0).all()

    @given(
        ys=st.lists(_y_px, min_size=2, max_size=30), thr=st.floats(min_value=0.0, max_value=100.0)
    )
    @settings(max_examples=40, database=None)
    def test_time_near_bottom_is_percentage(self, ys: list[float], thr: float) -> None:
        idx = _analyzer(ys).calculate_geotaxis_index(
            method="time_near_bottom", distance_threshold=thr
        )
        assert isinstance(idx, float)  # scalar for "time_near_bottom"
        assert 0.0 - 1e-9 <= idx <= 100.0 + 1e-9

    @given(ys=st.lists(_y_px, min_size=2, max_size=30), num_zones=_num_zones)
    @settings(max_examples=40, database=None)
    def test_zone_percentages_sum_to_100(self, ys: list[float], num_zones: int) -> None:
        zones = _analyzer(ys).calculate_geotaxis_index(
            method="zone_time", num_zones=num_zones, bottom_zones=1
        )
        assert isinstance(zones, dict)
        per_zone = sum(zones[f"zone_{i}_pct"] for i in range(num_zones))
        assert per_zone == pytest.approx(100.0, abs=1e-6)


@pytest.mark.property
class TestThigmotaxisInvariants:
    """Bounded-range invariants for thigmotaxis aggregates."""

    @given(
        ys=st.lists(_y_px, min_size=2, max_size=30),
        xs=st.lists(
            st.floats(min_value=1.0, max_value=999.0, allow_nan=False), min_size=2, max_size=30
        ),
        thr=st.floats(min_value=0.0, max_value=50.0),
    )
    @settings(max_examples=30, database=None)
    def test_time_near_wall_is_percentage(
        self, ys: list[float], xs: list[float], thr: float
    ) -> None:
        n = min(len(xs), len(ys))
        analyzer = _analyzer(ys[:n], xs=xs[:n])
        idx = analyzer.calculate_thigmotaxis_index(method="time_near_wall", distance_threshold=thr)
        if not np.isnan(idx):
            assert 0.0 - 1e-9 <= idx <= 100.0 + 1e-9

    @given(
        ys=st.lists(_y_px, min_size=2, max_size=30),
        xs=st.lists(
            st.floats(min_value=1.0, max_value=999.0, allow_nan=False), min_size=2, max_size=30
        ),
    )
    @settings(max_examples=30, database=None)
    def test_average_wall_distance_non_negative(self, ys: list[float], xs: list[float]) -> None:
        n = min(len(xs), len(ys))
        idx = _analyzer(ys[:n], xs=xs[:n]).calculate_thigmotaxis_index(method="average_distance")
        if not np.isnan(idx):
            assert idx >= 0.0 - 1e-9
