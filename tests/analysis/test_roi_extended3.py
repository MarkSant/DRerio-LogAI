"""Extended unit tests for analysis/roi.py."""

from __future__ import annotations

import pandas as pd

from zebtrack.analysis.roi import (
    _INTERIORS_INTERSECT,
    _assign_stable_roi,
    _first_not_none,
    _time_spent_in_rois,
    _to_seconds,
)


class TestRoiExtended3:
    """Test ROI predicates, helper functions, and stable assignment."""

    def test_interiors_intersect_constant(self):
        assert _INTERIORS_INTERSECT == "T********"

    def test_first_not_none(self):
        assert _first_not_none(None, 0, 5) == 0
        assert _first_not_none(None, 0.0, 10.0) == 0.0
        assert _first_not_none(None, None, "value") == "value"
        assert _first_not_none(None, None) is None

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
