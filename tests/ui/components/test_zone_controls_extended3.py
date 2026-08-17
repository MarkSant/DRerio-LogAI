"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig
from zebtrack.ui.components.zone_controls import ZoneControlsWidget, _hierarchy_labels


class TestZoneControlsExtended3:
    """Test ZoneControlsWidget state variables, multi-aquarium controls, and labels."""

    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels

    def test_widget_state_attributes(self):
        widget = object.__new__(ZoneControlsWidget)
        widget._roi_rule_config = RoiRuleConfig()

        assert widget._roi_rule_config.rule == "bbox_intersects"
        assert widget._roi_rule_config.buffer_radius_value == 0.5
