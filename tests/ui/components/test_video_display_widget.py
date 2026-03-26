"""Tests for VideoDisplayWidget component."""

from unittest.mock import Mock

import pytest
from PIL import Image

from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def event_bus():
    bus = Mock()
    bus.subscribe = Mock()
    return bus


@pytest.fixture
def widget(tkinter_root, event_bus):
    display = VideoDisplayWidget(tkinter_root, event_bus=event_bus, width=320, height=240)
    tkinter_root.update_idletasks()
    return display


@pytest.mark.gui
def test_get_image_size_defaults(widget):
    assert widget.get_image_size() == (320, 240)


@pytest.mark.gui
def test_set_image_updates_state(widget, monkeypatch):
    monkeypatch.setattr(widget.canvas, "winfo_width", lambda: 200)
    monkeypatch.setattr(widget.canvas, "winfo_height", lambda: 100)

    image = Image.new("RGB", (100, 50), color=(10, 20, 30))
    widget.set_image(image)

    widget._draw_bg_image_to_canvas()

    assert widget._original_image is image
    assert widget._raw_bg_image is image
    assert widget.get_image_size() == (100, 50)


@pytest.mark.gui
def test_coordinate_conversions(widget):
    widget._bg_scale = 2.0
    widget._bg_offset = (10, 20)

    assert widget.video_to_canvas(5, 5) == (20.0, 30.0)
    assert widget.canvas_to_video(20, 30) == (5.0, 5.0)


@pytest.mark.gui
def test_clear_resets_state(widget):
    widget._original_image = Image.new("RGB", (10, 10))
    widget._raw_bg_image = Image.new("RGB", (10, 10))
    widget._canvas_bg_image = Mock()
    widget._canvas_bg_position = (1, 1, "center")

    widget.clear()

    assert widget._original_image is None
    assert widget._raw_bg_image is None
    assert widget._canvas_bg_image is None
    assert widget._canvas_bg_position is None


@pytest.mark.gui
def test_load_frame_missing_path_emits_error(widget, event_bus, monkeypatch):
    monkeypatch.setattr("zebtrack.ui.components.video_display.os.path.exists", lambda _: False)

    assert widget.load_frame("missing.mp4") is False

    event_bus.publish.assert_called_once_with(
        UIEvents.FRAME_ERROR,
        {"reason": "video_not_found", "path": "missing.mp4"},
    )


@pytest.mark.gui
def test_on_canvas_resize_schedules_redraw(widget):
    widget._raw_bg_image = Image.new("RGB", (10, 10))

    widget._on_canvas_resize(Mock())

    assert widget._redraw_job is not None
