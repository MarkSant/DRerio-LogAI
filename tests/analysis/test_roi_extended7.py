"""Extended unit tests for analysis/roi.py (Part 7)."""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.roi import _time_spent_in_rois


class TestRoiExtended7:
    """Test ROI time spent calculations with custom stable indicators."""

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
