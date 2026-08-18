"""Extended unit tests for analysis/roi.py (Part 8)."""

from __future__ import annotations

from zebtrack.analysis.roi import _INTERIORS_INTERSECT, _first_not_none


class TestRoiExtended8:
    """Test ROI analysis helpers, DE-9IM pattern, and fallback resolver."""

    def test_first_not_none_all_none(self):
        assert _first_not_none(None, None, None) is None

    def test_first_not_none_with_values(self):
        assert _first_not_none(None, 42, 100) == 42
        assert _first_not_none(0, 5) == 0
        assert _first_not_none(0.0, 10.0) == 0.0
        assert _first_not_none(False, True) is False

    def test_interiors_intersect_pattern(self):
        assert _INTERIORS_INTERSECT == "T********"
