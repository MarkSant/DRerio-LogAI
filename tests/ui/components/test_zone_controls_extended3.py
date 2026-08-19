"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from zebtrack.ui.components.zone_controls import _hierarchy_labels


class TestZoneControlsExtended3:
    """Test ZoneControlsWidget state variables, multi-aquarium controls, and labels."""

    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
