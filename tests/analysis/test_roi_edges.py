"""Edge-case tests for ``zebtrack.analysis.roi.ROIAnalyzer``.

Complements ``test_roi_analyzer.py`` / ``test_roi_metrics.py`` with two behaviours
that matter scientifically but were not pinned:

* **Boundary semantics** — ``shapely.contains`` is strict, so a centroid sitting
  exactly on a ROI edge is *outside* (mirrors the production inclusion logic and
  contrasts with the cv2-based, boundary-inclusive check in ``zone_scaler``).
* **Flutter filter** — a single-frame presence blip shorter than
  ``flutter_n_frames`` must be suppressed, while a run of ``n`` consecutive
  frames is confirmed. This prevents spurious ROI entry/exit events.
"""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer


def _make_analyzer(x_cm_value: float, *, flutter_n_frames: int = 1) -> ROIAnalyzer:
    """Build an analyzer whose subject is stationary at ``x_cm_value`` (y=15cm)."""
    n = 5
    timestamps = pd.date_range(start="2023-01-01", periods=n, freq="100ms")
    trajectory_df = pd.DataFrame(
        {
            "x_cm_smoothed": np.full(n, x_cm_value),
            "y_cm_smoothed": np.full(n, 15.0),
            "x_center_px": np.full(n, x_cm_value * 10.0),
            "y_center_px": np.full(n, 150.0),
            "x1": np.full(n, x_cm_value * 10.0 - 5),
            "y1": np.full(n, 145.0),
            "x2": np.full(n, x_cm_value * 10.0 + 5),
            "y2": np.full(n, 155.0),
        },
        index=timestamps,
    )

    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory_df.copy()
    b_analyzer.pixelcm_x = 10.0
    b_analyzer._pixelcm_x = 10.0
    b_analyzer.pixelcm_y = 10.0
    b_analyzer._pixelcm_y = 10.0
    b_analyzer._video_height_px = 300

    roi = ROI(
        name="TestROI",
        geometry=Polygon([(10, 10), (20, 10), (20, 20), (10, 20)]),
        coordinate_space="cm",
    )
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[roi],
        flutter_n_frames=flutter_n_frames,
        inclusion_rule="centroid_in",
    )


class TestBoundarySemantics:
    def test_centroid_exactly_on_edge_is_outside(self):
        # x=10cm lies exactly on the ROI's left edge → strictly outside.
        analyzer = _make_analyzer(10.0)
        assert not analyzer._trajectory["in_TestROI_stable"].any()

    def test_centroid_strictly_inside_is_inside(self):
        analyzer = _make_analyzer(15.0)
        assert analyzer._trajectory["in_TestROI_stable"].all()


class TestFlutterFilter:
    def test_single_frame_blip_is_suppressed(self):
        analyzer = _make_analyzer(15.0, flutter_n_frames=3)
        raw = pd.Series([False, False, True, False, False])
        stable = analyzer._apply_flutter_filter(raw)
        # The lone True must not survive a 3-frame stability window.
        assert not stable.iloc[2]
        assert not stable.any()

    def test_sustained_run_is_confirmed(self):
        analyzer = _make_analyzer(15.0, flutter_n_frames=3)
        raw = pd.Series([False, True, True, True, False])
        stable = analyzer._apply_flutter_filter(raw)
        # Once n consecutive True frames accumulate, presence is confirmed.
        assert bool(stable.iloc[3]) is True

    def test_flutter_n_one_is_passthrough(self):
        analyzer = _make_analyzer(15.0, flutter_n_frames=1)
        raw = pd.Series([False, True, False, True, True])
        stable = analyzer._apply_flutter_filter(raw)
        pd.testing.assert_series_equal(stable, raw, check_names=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
