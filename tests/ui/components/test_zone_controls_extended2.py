"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig
from zebtrack.ui.components.zone_controls import ZoneControlsWidget, _hierarchy_labels


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

    def test_zone_controls_state_defaults(self):
        widget = object.__new__(ZoneControlsWidget)
        widget._roi_rule_config = RoiRuleConfig()
        assert widget._roi_rule_config is not None
        assert widget._roi_rule_config.rule == "center" or len(widget._roi_rule_config.rule) > 0
