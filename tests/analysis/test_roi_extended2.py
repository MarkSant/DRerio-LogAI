"""Extended unit tests for analysis/roi.py."""

from __future__ import annotations

import pandas as pd

from zebtrack.analysis.roi import (
    _INTERIORS_INTERSECT,
    _assign_stable_roi,
    _distance_in_rois,
    _entry_counts,
    _exit_counts,
    _first_not_none,
    _time_spent_in_rois,
    _to_seconds,
)


class TestRoiExtended2:
    """Test ROI analysis constants, metrics, entries/exits, and helper functions."""

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
