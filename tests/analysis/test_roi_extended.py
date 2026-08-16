"""
Extended unit tests for ROI behavioral analysis in analysis/roi.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import (
    ROI,
    ROIAnalyzer,
    _assign_stable_roi,
    _distance_in_rois,
    _entry_counts,
    _exit_counts,
    _first_not_none,
    _latency_to_first_entry,
    _time_spent_in_rois,
    _to_seconds,
)


class TestROIExtended:
    """Test ROI helper functions, metrics calculations, and time conversions."""

    def test_first_not_none(self):
        assert _first_not_none(None, None, 0, 5) == 0
        assert _first_not_none(None, "val", "fallback") == "val"
        assert _first_not_none(None, None) is None
        assert _first_not_none(False, True) is False

    def test_to_seconds(self):
        td = pd.Timedelta(seconds=5, milliseconds=500)
        assert _to_seconds(td) == 5.5
        assert _to_seconds(12.3) == 12.3

    def test_assign_stable_roi(self):
        df = pd.DataFrame(
            {
                "in_Center_stable": [False, True, False],
                "in_Periphery_stable": [True, False, False],
            }
        )
        _assign_stable_roi(df, ["Center", "Periphery"])
        assert df["stable_roi"].tolist() == ["Periphery", "Center", "Outside"]

    def test_time_spent_in_rois(self):
        df = pd.DataFrame(
            {
                "dt": [1.0, 1.0, 2.0, 1.0],
                "in_ZoneA_stable": [True, True, False, False],
                "in_ZoneB_stable": [False, False, True, False],
            }
        )
        res = _time_spent_in_rois(df, ["ZoneA", "ZoneB"])
        assert res["ZoneA"]["seconds"] == 2.0
        assert res["ZoneA"]["percentage"] == pytest.approx(40.0)
        assert res["ZoneB"]["seconds"] == 2.0
        assert res["ZoneB"]["percentage"] == pytest.approx(40.0)

    def test_time_spent_in_rois_zero_dt(self):
        df = pd.DataFrame(
            {
                "dt": [0.0, 0.0],
                "in_ZoneA_stable": [False, False],
            }
        )
        res = _time_spent_in_rois(df, ["ZoneA"])
        assert res["ZoneA"]["seconds"] == 0.0
        assert res["ZoneA"]["percentage"] == 0.0

    def test_latency_to_first_entry(self):
        idx = pd.to_datetime(["2026-08-16 10:00:00", "2026-08-16 10:00:05", "2026-08-16 10:00:10"])
        df = pd.DataFrame(
            {
                "in_Center_stable": [False, True, True],
                "in_Edge_stable": [False, False, False],
            },
            index=idx,
        )
        res = _latency_to_first_entry(df, ["Center", "Edge"])
        assert res["Center"] == 5.0
        assert res["Edge"] is None

    def test_entry_and_exit_counts(self):
        df = pd.DataFrame(
            {
                "in_ZoneA_stable": [False, True, True, False, True, False],
            }
        )
        entries = _entry_counts(df, ["ZoneA"])
        exits = _exit_counts(df, ["ZoneA"])
        assert entries["ZoneA"] == 2
        assert exits["ZoneA"] == 2

    def test_distance_in_rois(self):
        df = pd.DataFrame(
            {
                "x_cm_smoothed": [0.0, 3.0, 3.0, 7.0],
                "y_cm_smoothed": [0.0, 4.0, 4.0, 4.0],
                "in_ZoneA_stable": [False, True, True, False],
            }
        )
        dist = _distance_in_rois(df, ["ZoneA"])
        assert dist["ZoneA"] == pytest.approx(5.0)

    def test_roi_class_initialization(self):
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        roi = ROI(name="Arena1", geometry=poly, coordinate_space="cm")
        assert roi.name == "Arena1"
        assert roi.geometry == poly
        assert roi.coordinate_space == "cm"

    def test_roi_analyzer_initialization(self):
        n = 20
        timestamps = pd.timedelta_range(start="0s", periods=n, freq="100ms")
        x = np.linspace(10.0, 50.0, n)
        y = np.linspace(20.0, 60.0, n)
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x,
                "y_center_px": y,
                "x1": x - 5.0,
                "y1": y - 5.0,
                "x2": x + 5.0,
                "y2": y + 5.0,
            },
            index=timestamps,
        )
        arena = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        ba = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
            arena_polygon_px=arena,
            fps=10.0,
        )
        roi_poly = Polygon([(1, 1), (5, 1), (5, 5), (1, 5)])
        roi_obj = ROI(name="Center", geometry=roi_poly, coordinate_space="cm")
        analyzer = ROIAnalyzer(
            behavior_analyzer=ba,
            rois=[roi_obj],
            inclusion_rule="centroid_in",
        )
        assert "Center" in analyzer._rois
        assert analyzer._inclusion_rule == "centroid_in"
