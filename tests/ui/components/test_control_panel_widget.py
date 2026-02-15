"""Tests for ControlPanelWidget."""

from unittest.mock import Mock

import pytest

from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.events import Events


@pytest.fixture
def event_bus():
    bus = Mock()
    bus.publish_event = Mock()
    bus.subscribe = Mock()
    return bus


@pytest.fixture
def widget(tkinter_root, event_bus):
    panel = ControlPanelWidget(tkinter_root, event_bus=event_bus)
    tkinter_root.update_idletasks()
    event_bus.publish_event.reset_mock()
    return panel


@pytest.mark.gui
def test_recording_buttons_publish_events(widget, event_bus):
    widget._on_start_recording_clicked()
    event_bus.publish_event.assert_called_with(Events.RECORDING_START, {})

    event_bus.publish_event.reset_mock()
    widget._on_stop_recording_clicked()
    event_bus.publish_event.assert_called_with(Events.RECORDING_STOP, {})


@pytest.mark.gui
def test_process_video_publishes_event(widget, event_bus):
    widget._on_process_video_clicked()
    event_bus.publish_event.assert_called_with(Events.UI_REQUEST_PROCESS_VIDEOS, {})


@pytest.mark.gui
def test_preview_toggle_emits_event(widget, event_bus):
    widget.show_preview_var.set(False)
    widget._on_preview_toggled()

    event_bus.publish_event.assert_called_with(
        event_name="control.preview_toggled", data={"enabled": False}
    )


@pytest.mark.gui
def test_interval_changed_emits_event(widget, event_bus):
    widget.processing_interval_var.set("15")
    widget._on_interval_changed()

    event_bus.publish_event.assert_called_with(
        event_name="control.interval_changed", data={"interval": 15}
    )


@pytest.mark.gui
def test_interval_changed_invalid_no_event(widget, event_bus):
    widget.processing_interval_var.set("abc")
    widget._on_interval_changed()

    event_bus.publish_event.assert_not_called()


@pytest.mark.gui
def test_set_recording_state(widget):
    widget.set_recording_state(True)
    assert str(widget.start_rec_btn["state"]) == "disabled"
    assert str(widget.stop_rec_btn["state"]) == "normal"

    widget.set_recording_state(False)
    assert str(widget.start_rec_btn["state"]) == "normal"
    assert str(widget.stop_rec_btn["state"]) == "disabled"


@pytest.mark.gui
def test_set_processing_enabled(widget):
    widget.set_processing_enabled(False)
    assert str(widget.process_video_btn["state"]) == "disabled"

    widget.set_processing_enabled(True)
    assert str(widget.process_video_btn["state"]) == "normal"
