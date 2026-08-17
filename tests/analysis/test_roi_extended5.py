"""Extended unit tests for analysis/roi.py (Part 5)."""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.roi import _first_not_none, _time_spent_in_rois, _to_seconds


class TestRoiExtended5:
    """Test ROI time calculations and candidate resolution fallbacks."""

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
