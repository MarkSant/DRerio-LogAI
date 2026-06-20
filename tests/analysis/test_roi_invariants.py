"""Property-based invariants for ROI occupancy and entry/exit metrics.

``tests/analysis/test_roi_metrics.py`` pins golden values on a hand-built
crossing trajectory, and ``tests/test_property_roi.py`` covers only the flutter
filter. Neither asserts the *physical invariants* of the per-ROI numbers that go
into the summary/report: a time percentage must stay in ``[0, 100]``, time in
mutually-exclusive ROIs cannot exceed the session, and entries/exits must be
balanced (an animal can finish at most one ROI mid-visit).

ROIs use the ``centroid_in`` rule with disjoint geometries so a frame belongs to
at most one ROI -- the precondition for the "sum <= 100 %" invariant.

Style mirrors ``tests/test_property_zone_scaler.py`` (``.map``-based strategies,
``database=None``, ``@pytest.mark.property``).
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer

_FRAME = 600
_ARENA_PX = [[0, 0], [_FRAME, 0], [_FRAME, _FRAME], [0, _FRAME]]

# Two disjoint square ROIs in pixel space.
_ROIS = [
    ROI(
        name="A",
        geometry=Polygon([(0, 0), (200, 0), (200, 200), (0, 200)]),
        coordinate_space="px",
    ),
    ROI(
        name="B",
        geometry=Polygon([(350, 350), (550, 350), (550, 550), (350, 550)]),
        coordinate_space="px",
    ),
]


def _roi_analyzer(xs: list[float], ys: list[float]) -> ROIAnalyzer:
    n = len(xs)
    df = pd.DataFrame(
        {
            "timestamp": [i / 30.0 for i in range(n)],
            "x_center_px": xs,
            "y_center_px": ys,
            "x1": [x - 5 for x in xs],
            "y1": [y - 5 for y in ys],
            "x2": [x + 5 for x in xs],
            "y2": [y + 5 for y in ys],
        }
    )
    b_analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=_FRAME,
        arena_polygon_px=_ARENA_PX,
        fps=30.0,
        window_length=1,
        polyorder=0,
    )
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=_ROIS,
        flutter_n_frames=1,
        inclusion_rule="centroid_in",
    )


_px = st.floats(min_value=0.0, max_value=float(_FRAME), allow_nan=False, allow_infinity=False)


@pytest.mark.property
class TestRoiOccupancyInvariants:
    """Per-ROI time is a bounded, conserved quantity."""

    @given(
        xs=st.lists(_px, min_size=6, max_size=40),
        ys=st.lists(_px, min_size=6, max_size=40),
    )
    @settings(max_examples=40, database=None)
    def test_time_percentage_bounded(self, xs: list[float], ys: list[float]) -> None:
        n = min(len(xs), len(ys))
        time_spent = _roi_analyzer(xs[:n], ys[:n]).get_time_spent_in_rois()
        for stats in time_spent.values():
            assert stats["seconds"] >= 0.0
            assert -1e-9 <= stats["percentage"] <= 100.0 + 1e-9

    @given(
        xs=st.lists(_px, min_size=6, max_size=40),
        ys=st.lists(_px, min_size=6, max_size=40),
    )
    @settings(max_examples=40, database=None)
    def test_disjoint_roi_time_sum_within_session(self, xs: list[float], ys: list[float]) -> None:
        """Time across mutually-exclusive ROIs cannot exceed the whole session."""
        n = min(len(xs), len(ys))
        time_spent = _roi_analyzer(xs[:n], ys[:n]).get_time_spent_in_rois()
        total_pct = sum(stats["percentage"] for stats in time_spent.values())
        assert total_pct <= 100.0 + 1e-9


@pytest.mark.property
class TestRoiEntryExitInvariants:
    """Entries and exits are non-negative and balanced to within one visit."""

    @given(
        xs=st.lists(_px, min_size=6, max_size=40),
        ys=st.lists(_px, min_size=6, max_size=40),
    )
    @settings(max_examples=40, database=None)
    def test_entries_exits_balanced(self, xs: list[float], ys: list[float]) -> None:
        n = min(len(xs), len(ys))
        analyzer = _roi_analyzer(xs[:n], ys[:n])
        entries = analyzer.get_entry_counts()
        exits = analyzer.get_exit_counts()
        for name in ("A", "B"):
            assert entries[name] >= 0
            assert exits[name] >= 0
            # Finishing inside (entry without exit) or starting inside then leaving
            # (exit without entry) differ by at most one.
            assert abs(int(entries[name]) - int(exits[name])) <= 1
