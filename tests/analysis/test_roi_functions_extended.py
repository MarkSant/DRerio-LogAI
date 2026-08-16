"""Extended unit tests for analysis/roi.py functions and ROI container."""

from __future__ import annotations

import pandas as pd
from shapely.geometry import Polygon

from zebtrack.analysis.roi import (
    ROI,
    _assign_stable_roi,
    _distance_in_rois,
    _entry_counts,
    _exit_counts,
    _first_not_none,
    _latency_to_first_entry,
    _time_spent_in_rois,
    _to_seconds,
)


class TestRoiHelpersExtended:
    """Test helper functions in analysis/roi.py."""

    def test_first_not_none(self):
        assert _first_not_none(None, None, 0, 5) == 0
        assert _first_not_none(None, 0.0, 10) == 0.0
        assert _first_not_none(None, "val") == "val"
        assert _first_not_none(None, None) is None

    def test_to_seconds(self):
        td = pd.Timedelta(seconds=12.5)
        assert _to_seconds(td) == 12.5
        assert _to_seconds(42) == 42.0
        assert _to_seconds(3.14) == 3.14

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
                "dt": [1.0, 1.0, 2.0],
                "in_ZoneA_stable": [True, True, False],
                "in_ZoneB_stable": [False, False, True],
            }
        )
        times = _time_spent_in_rois(df, ["ZoneA", "ZoneB"])
        assert times["ZoneA"]["seconds"] == 2.0
        assert times["ZoneA"]["percentage"] == 50.0
        assert times["ZoneB"]["seconds"] == 2.0
        assert times["ZoneB"]["percentage"] == 50.0

    def test_time_spent_in_rois_empty_total_time(self):
        df = pd.DataFrame(
            {
                "dt": [0.0, 0.0],
                "in_ZoneA_stable": [True, False],
            }
        )
        times = _time_spent_in_rois(df, ["ZoneA"])
        assert times["ZoneA"]["seconds"] == 0.0
        assert times["ZoneA"]["percentage"] == 0.0

    def test_entry_and_exit_counts(self):
        # Timeline: False -> True -> True -> False -> True
        df = pd.DataFrame(
            {
                "in_ZoneA_stable": [False, True, True, False, True],
            }
        )
        entries = _entry_counts(df, ["ZoneA"])
        exits = _exit_counts(df, ["ZoneA"])
        assert entries["ZoneA"] == 2
        assert exits["ZoneA"] == 1

    def test_latency_to_first_entry(self):
        # Index with timestamps
        index = pd.to_datetime(
            ["2026-01-01 00:00:00", "2026-01-01 00:00:05", "2026-01-01 00:00:10"]
        )
        df = pd.DataFrame(
            {
                "in_ZoneA_stable": [False, True, True],
                "in_ZoneB_stable": [False, False, False],
            },
            index=index,
        )
        latency = _latency_to_first_entry(df, ["ZoneA", "ZoneB"])
        assert latency["ZoneA"] == 5.0
        assert latency["ZoneB"] is None

    def test_distance_in_rois(self):
        df = pd.DataFrame(
            {
                "x_cm_smoothed": [0.0, 3.0, 3.0],
                "y_cm_smoothed": [0.0, 4.0, 4.0],
                "in_ZoneA_stable": [False, True, False],
            }
        )
        dists = _distance_in_rois(df, ["ZoneA"])
        # Distance at step 1: sqrt(3^2 + 4^2) = 5.0
        assert dists["ZoneA"] == 5.0

    def test_roi_container(self):
        poly = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
        roi = ROI("Central", poly, coordinate_space="cm")
        assert roi.name == "Central"
        assert roi.geometry.area == 100.0
        assert roi.coordinate_space == "cm"
