"""Extended unit tests for ZoneControlsWidget in ui/components/zone_controls.py."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

import pytest

from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig
from zebtrack.ui.components.zone_controls import (
    ZoneControlsWidget,
    _hierarchy_labels,
)


class TestZoneControlsExtended:
    """Test hierarchy labels, widget initialization, and state variables."""

    @pytest.fixture
    def root(self):
        try:
            r = tk.Tk()
            r.withdraw()
            yield r
            r.destroy()
        except tk.TclError:
            pytest.skip("Tkinter display not available")

    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
        assert len(labels) == 3

    def test_zone_controls_widget_initialization(self, root):
        event_bus = MagicMock()
        cfg = RoiRuleConfig(rule="centroid_in", buffer_radius_value=1.5)
        widget = ZoneControlsWidget(
            parent=root,
            event_bus=event_bus,
            roi_rule_config=cfg,
        )

        assert widget._roi_rule_config is cfg
        assert widget.aquarium_count_var.get() == 1
        assert widget.active_aquarium_var.get() == 0
        assert widget.sequential_processing_var.get() is True
        assert widget.roi_choice_var.get() == "none"

    def test_set_roi_rule_config(self, root):
        widget = ZoneControlsWidget(parent=root)
        new_cfg = RoiRuleConfig(rule="bbox_intersects", min_bbox_overlap_ratio=0.25)
        widget.set_roi_rule_config(new_cfg)
        assert widget._roi_rule_config is new_cfg

    def test_update_template_list_and_clear_zone_list(self, root):
        widget = ZoneControlsWidget(parent=root)
        # Template list update
        widget.update_template_list(["Template1", "Template2"])
        # Clear zone list safely
        widget.clear_zone_list()

    def test_interactive_buttons_toggle(self, root):
        widget = ZoneControlsWidget(parent=root)
        widget.show_interactive_buttons(freehand_drawing=True)
        widget.hide_interactive_buttons()
        widget.show_interactive_buttons(freehand_drawing=False)
        widget.hide_interactive_buttons()
