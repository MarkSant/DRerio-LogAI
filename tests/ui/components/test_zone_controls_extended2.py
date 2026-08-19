"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from zebtrack.ui.components.zone_controls import _hierarchy_labels


class TestZoneControlsExtended2:
    """Test ZoneControlsWidget hierarchy labels and widget default variables."""

    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
        assert labels["group"] == "Group" or "Grupo" in labels["group"]
        assert labels["day"] == "Day" or "Dia" in labels["day"]
        assert labels["subject"] == "Subject" or "Sujeito" in labels["subject"]
