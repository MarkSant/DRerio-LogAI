"""Tests for ZoneControlsWidget core behaviors."""

from unittest.mock import Mock

import pytest

from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def event_bus():
    bus = Mock()
    bus.publish = Mock()
    bus.subscribe = Mock()
    return bus


@pytest.fixture
def widget(tkinter_root, event_bus):
    zone_widget = ZoneControlsWidget(tkinter_root, event_bus=event_bus)
    tkinter_root.update_idletasks()
    event_bus.publish.reset_mock()
    return zone_widget


@pytest.mark.gui
def test_set_draw_roi_enabled(widget):
    widget.set_draw_roi_enabled(True)

    assert str(widget.draw_roi_button["state"]) == "normal"
    assert str(widget.conclude_video_btn["state"]) == "normal"

    widget.set_draw_roi_enabled(False)

    assert str(widget.draw_roi_button["state"]) == "disabled"
    assert str(widget.conclude_video_btn["state"]) == "disabled"


@pytest.mark.gui
def test_update_template_list(widget):
    widget.update_template_list(["A", "B"])

    assert widget.roi_template_combobox["values"] == ("A", "B")


@pytest.mark.gui
def test_add_and_clear_zone_list(widget):
    widget.add_zone_to_list("zone-1", "Arena", "Polígono", "Azul")
    widget.add_zone_to_list("zone-2", "ROI 1", "ROI", "Vermelho")

    assert len(widget.zone_listbox.get_children("")) == 2

    widget.clear_zone_list()

    assert widget.zone_listbox.get_children("") == ()


@pytest.mark.gui
def test_get_video_path_from_item(widget):
    item_id = widget.video_selector_tree.insert("", "end", tags=("C:/video.mp4",))

    assert widget._get_video_path_from_item(item_id) == "C:/video.mp4"

    no_path_id = widget.video_selector_tree.insert("", "end", tags=("not_a_path",))

    assert widget._get_video_path_from_item(no_path_id) is None


@pytest.mark.gui
def test_toggle_video_tree_label(widget):
    widget._video_tree_expanded = True
    widget._update_video_tree_toggle_label()
    assert widget.video_tree_toggle_btn.cget("text") == "Recolher tudo"

    widget._video_tree_expanded = False
    widget._update_video_tree_toggle_label()
    assert widget.video_tree_toggle_btn.cget("text") == "Expandir tudo"


@pytest.mark.gui
def test_on_roi_rule_changed_emits_event(widget, event_bus):
    widget.roi_inclusion_rule_var.set("centroid_in_on_buffered_roi")
    widget._on_roi_rule_changed(None)

    event_bus.publish.assert_called_with(
        UIEvents.DETECTOR_UPDATE_PARAMETERS,
        {"rule": "centroid_in_on_buffered_roi"},
    )
    assert "centroide" in widget.rule_help_label.cget("text")


@pytest.mark.gui
def test_apply_roi_settings_emits_event(widget, event_bus):
    widget.roi_inclusion_rule_var.set("bbox_intersects")
    widget.roi_buffer_radius_var.set("1.2")
    widget.roi_overlap_ratio_var.set("0.25")

    widget._on_apply_roi_settings_clicked()

    event_bus.publish.assert_called_with(
        UIEvents.DETECTOR_UPDATE_PARAMETERS,
        {"rule": "bbox_intersects", "buffer_radius": 1.2, "overlap_ratio": 0.25},
    )


@pytest.mark.gui
def test_on_video_search_changed_emits_event(widget, event_bus):
    widget.video_search_var.set("demo")
    widget._on_video_search_changed()

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_VIDEO_SEARCH_CHANGED,
        {"search_text": "demo"},
    )


@pytest.mark.gui
def test_on_video_tree_double_click_emits_event(widget, event_bus):
    item_id = widget.video_selector_tree.insert("", "end")
    widget.video_selector_tree.selection_set(item_id)

    widget._on_video_tree_double_click(Mock())

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_VIDEO_DOUBLE_CLICK,
        {"item_id": item_id},
    )
