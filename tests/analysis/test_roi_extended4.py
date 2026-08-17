"""Extended unit tests for analysis/roi.py (Part 4)."""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.analysis.roi import (
    _distance_in_rois,
    _entry_counts,
    _exit_counts,
    _latency_to_first_entry,
)


class TestRoiExtended4:
    """Test ROI transition calculations: entry, exit, distance, and latency."""

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
