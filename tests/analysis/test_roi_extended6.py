"""Extended unit tests for analysis/roi.py (Part 6)."""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.roi import _time_spent_in_rois


class TestRoiExtended6:
    """Test ROI zone analysis calculation with multiple zones."""

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
