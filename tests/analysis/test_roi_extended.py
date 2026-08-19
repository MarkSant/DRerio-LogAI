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
    _INTERIORS_INTERSECT,
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


class TestRoiExtended2:
    def test_interiors_intersect_constant(self):
        assert _INTERIORS_INTERSECT == "T********"

    def test_first_not_none(self):
        assert _first_not_none(None, None, 0, 5) == 0
        assert _first_not_none(None, 0.0, 10.0) == 0.0
        assert _first_not_none(None, None, None) is None
        assert _first_not_none("first", "second") == "first"

    def test_to_seconds(self):
        assert _to_seconds(15.5) == 15.5
        td = pd.Timedelta(seconds=42.5)
        assert _to_seconds(td) == 42.5

    def test_assign_stable_roi(self):
        df = pd.DataFrame(
            {
                "in_Center_stable": [True, False, False],
                "in_Periphery_stable": [False, True, False],
            }
        )
        _assign_stable_roi(df, ["Center", "Periphery"])
        assert df["stable_roi"].tolist() == ["Center", "Periphery", "Outside"]

    def test_time_spent_in_rois(self):
        df = pd.DataFrame(
            {
                "dt": [1.0, 2.0, 1.0],
                "in_Center_stable": [True, True, False],
                "in_Periphery_stable": [False, False, True],
            }
        )
        results = _time_spent_in_rois(df, ["Center", "Periphery"])
        assert results["Center"]["seconds"] == 3.0
        assert results["Center"]["percentage"] == 75.0
        assert results["Periphery"]["seconds"] == 1.0
        assert results["Periphery"]["percentage"] == 25.0

    def test_entry_and_exit_counts(self):
        df = pd.DataFrame(
            {
                "in_Center_stable": [False, True, True, False, True],
            }
        )
        entries = _entry_counts(df, ["Center"])
        exits = _exit_counts(df, ["Center"])

        assert entries["Center"] == 2
        assert exits["Center"] == 1

    def test_distance_in_rois(self):
        df = pd.DataFrame(
            {
                "x_cm_smoothed": [0.0, 3.0, 3.0],
                "y_cm_smoothed": [0.0, 4.0, 4.0],
                "in_ZoneA_stable": [True, True, False],
            }
        )
        dists = _distance_in_rois(df, ["ZoneA"])
        assert dists["ZoneA"] == 5.0


class TestRoiExtended3:
    def test_interiors_intersect_constant(self):
        assert _INTERIORS_INTERSECT == "T********"

    def test_first_not_none(self):
        assert _first_not_none(None, 0, 5) == 0
        assert _first_not_none(None, 0.0, 10.0) == 0.0
        assert _first_not_none(None, None, "value") == "value"
        assert _first_not_none(None, None) is None

    def test_assign_stable_roi(self):
        df = pd.DataFrame(
            {
                "in_Center_stable": [True, False, False],
                "in_Periphery_stable": [False, True, False],
            }
        )
        _assign_stable_roi(df, ["Center", "Periphery"])

        assert list(df["stable_roi"]) == ["Center", "Periphery", "Outside"]

    def test_time_spent_in_rois_zero_dt(self):
        df = pd.DataFrame(
            {
                "dt": [0.0, 0.0],
                "in_Center_stable": [True, False],
            }
        )
        res = _time_spent_in_rois(df, ["Center"])
        assert res["Center"]["seconds"] == 0.0
        assert res["Center"]["percentage"] == 0.0


class TestRoiExtended4:
    def test_entry_and_exit_counts(self):
        df = pd.DataFrame(
            {
                "in_Center_stable": [False, True, True, False, True],
                "in_Periphery_stable": [True, False, False, True, False],
            }
        )

        entries = _entry_counts(df, ["Center", "Periphery"])
        exits = _exit_counts(df, ["Center", "Periphery"])

        assert entries["Center"] == 2
        assert exits["Center"] == 1
        assert entries["Periphery"] == 1
        assert exits["Periphery"] == 2

    def test_distance_in_rois(self):
        df = pd.DataFrame(
            {
                "x_cm_smoothed": [0.0, 3.0, 3.0, 3.0],
                "y_cm_smoothed": [0.0, 4.0, 4.0, 4.0],
                "in_ZoneA_stable": [False, True, True, False],
            }
        )

        dists = _distance_in_rois(df, ["ZoneA"])
        assert dists["ZoneA"] == pytest.approx(5.0)

    def test_latency_to_first_entry_never_entered(self):
        df = pd.DataFrame(
            {
                "in_Never_stable": [False, False, False],
            },
            index=[0.0, 1.0, 2.0],
        )

        latency = _latency_to_first_entry(df, ["Never"])
        assert latency["Never"] is None


class TestRoiExtended5:
    def test_time_in_rois_zero_total_time(self):
        df = pd.DataFrame({"dt": [0.0], "in_ZoneA_stable": [False]})
        res = _time_spent_in_rois(df, ["ZoneA"])
        assert res == {"ZoneA": {"seconds": 0.0, "percentage": 0.0}}

    def test_time_in_rois_positive_duration(self):
        df = pd.DataFrame(
            {
                "dt": [1.0, 1.0, 1.0, 1.0],
                "in_ZoneA_stable": [True, True, False, False],
            }
        )
        res = _time_spent_in_rois(df, ["ZoneA"])
        assert res["ZoneA"]["seconds"] == 2.0
        assert res["ZoneA"]["percentage"] == pytest.approx(50.0)

    def test_first_not_none(self):
        assert _first_not_none(None, "first", "second") == "first"
        assert _first_not_none(None, None, 42) == 42
        assert _first_not_none(None, None) is None

    def test_to_seconds_numeric_and_timedelta(self):
        assert _to_seconds(10.5) == 10.5
        assert _to_seconds(0) == 0.0
        td = pd.Timedelta(seconds=5.25)
        assert _to_seconds(td) == 5.25


class TestRoiExtended6:
    def test_time_in_multiple_rois(self):
        df = pd.DataFrame(
            {
                "dt": [1.0, 1.0, 1.0, 1.0],
                "in_ZoneA_stable": [True, True, False, False],
                "in_ZoneB_stable": [False, False, True, True],
            }
        )
        res = _time_spent_in_rois(df, ["ZoneA", "ZoneB"])
        assert res["ZoneA"]["seconds"] == 2.0
        assert res["ZoneB"]["seconds"] == 2.0
        assert res["ZoneA"]["percentage"] == pytest.approx(50.0)
        assert res["ZoneB"]["percentage"] == pytest.approx(50.0)

    def test_time_in_empty_rois_list(self):
        df = pd.DataFrame({"dt": [1.0, 1.0]})
        res = _time_spent_in_rois(df, [])
        assert res == {}


class TestRoiExtended7:
    def test_time_spent_in_single_roi_full_time(self):
        df = pd.DataFrame(
            {
                "dt": [0.5, 0.5, 0.5, 0.5],
                "in_Center_stable": [True, True, True, True],
            }
        )
        res = _time_spent_in_rois(df, ["Center"])
        assert res["Center"]["seconds"] == 2.0
        assert res["Center"]["percentage"] == pytest.approx(100.0)

    def test_time_spent_in_single_roi_zero_time(self):
        df = pd.DataFrame(
            {
                "dt": [0.5, 0.5, 0.5, 0.5],
                "in_Center_stable": [False, False, False, False],
            }
        )
        res = _time_spent_in_rois(df, ["Center"])
        assert res["Center"]["seconds"] == 0.0
        assert res["Center"]["percentage"] == pytest.approx(0.0)

    def test_time_spent_in_rois_partial_percentages(self):
        df = pd.DataFrame(
            {
                "dt": [1.0, 1.0, 1.0, 1.0],
                "in_Inner_stable": [True, False, False, False],
            }
        )
        res = _time_spent_in_rois(df, ["Inner"])
        assert res["Inner"]["seconds"] == 1.0
        assert res["Inner"]["percentage"] == pytest.approx(25.0)


class TestRoiExtended8:
    def test_first_not_none_all_none(self):
        assert _first_not_none(None, None, None) is None

    def test_first_not_none_with_values(self):
        assert _first_not_none(None, 42, 100) == 42
        assert _first_not_none(0, 5) == 0
        assert _first_not_none(0.0, 10.0) == 0.0
        assert _first_not_none(False, True) is False

    def test_interiors_intersect_pattern(self):
        assert _INTERIORS_INTERSECT == "T********"
