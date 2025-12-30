"""
Tests for ConfigEditorWidget component.
"""

import pytest

from zebtrack.ui.components.config_editor import ConfigEditorWidget
from zebtrack.ui.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create an event bus instance."""
    return EventBus()


@pytest.fixture
def config_widget(tkinter_root, event_bus):
    """Create a ConfigEditorWidget instance for testing."""
    widget = ConfigEditorWidget(tkinter_root, event_bus=event_bus)
    widget.pack()
    tkinter_root.update()
    return widget


def test_widget_initialization(config_widget):
    """Test that widget initializes with default values."""
    assert config_widget.fps_var.get() == "30"
    assert config_widget.processing_interval_var.get() == "10"
    assert config_widget.processing_offset_var.get() == "0"
    assert config_widget.window_length_var.get() == "7"
    assert config_widget.polyorder_var.get() == "3"
    assert config_widget.flush_interval_var.get() == "5.0"
    assert config_widget.flush_rows_var.get() == "500"
    assert config_widget.roi_inclusion_rule_var.get() == "centroid_in"
    assert config_widget.roi_buffer_radius_var.get() == "0"
    assert config_widget.roi_overlap_ratio_var.get() == "0.5"


def test_get_values_returns_correct_structure(config_widget):
    """Test that get_values returns correctly structured dict."""
    values = config_widget.get_values()

    assert "video_processing" in values
    assert "trajectory_smoothing" in values
    assert "recorder" in values
    assert "roi_inclusion_rule" in values
    assert "roi_buffer_radius_value" in values
    assert "roi_min_bbox_overlap_ratio" in values

    assert values["video_processing"]["fps"] == 30
    assert values["video_processing"]["processing_interval"] == 10
    assert values["video_processing"]["processing_offset"] == 0
    assert values["trajectory_smoothing"]["window_length"] == 7
    assert values["trajectory_smoothing"]["polyorder"] == 3
    assert values["recorder"]["flush_interval_seconds"] == 5.0
    assert values["recorder"]["flush_row_threshold"] == 500
    assert values["roi_inclusion_rule"] == "centroid_in"
    assert values["roi_buffer_radius_value"] == 0.0
    assert values["roi_min_bbox_overlap_ratio"] == 0.5


def test_set_values_populates_form_correctly(config_widget):
    """Test that set_values correctly populates all form fields."""
    test_values = {
        "video_processing": {
            "fps": 60,
            "processing_interval": 5,
            "processing_offset": 10,
        },
        "trajectory_smoothing": {
            "window_length": 9,
            "polyorder": 4,
        },
        "recorder": {
            "flush_interval_seconds": 10.0,
            "flush_row_threshold": 1000,
        },
        "roi_inclusion_rule": "bbox_intersects",
        "roi_buffer_radius_value": 5.0,
        "roi_min_bbox_overlap_ratio": 0.7,
    }

    config_widget.set_values(test_values)

    assert config_widget.fps_var.get() == "60"
    assert config_widget.processing_interval_var.get() == "5"
    assert config_widget.processing_offset_var.get() == "10"
    assert config_widget.window_length_var.get() == "9"
    assert config_widget.polyorder_var.get() == "4"
    assert config_widget.flush_interval_var.get() == "10.0"
    assert config_widget.flush_rows_var.get() == "1000"
    assert config_widget.roi_inclusion_rule_var.get() == "bbox_intersects"
    assert config_widget.roi_buffer_radius_var.get() == "5.0"
    assert config_widget.roi_overlap_ratio_var.get() == "0.7"


def test_event_emission_on_save(config_widget, event_bus):
    """Test that save button emits config.save_requested event to queue."""
    # Clear any events from widget initialization
    while not event_bus._queue.empty():
        event_bus._queue.get_nowait()

    # Trigger save
    config_widget._on_save_clicked()

    # Check event was added to queue
    assert not event_bus._queue.empty()
    event = event_bus._queue.get_nowait()
    assert event.payload.event_name == "config.save_requested"
    assert "values" in event.payload.data


def test_event_emission_on_reset(config_widget, event_bus):
    """Test that reset button emits config.reset_requested event to queue."""
    # Clear any events from widget initialization (BehavioralConfigWidget emits events)
    while not event_bus._queue.empty():
        event_bus._queue.get_nowait()

    # Trigger reset
    config_widget._on_reset_clicked()

    # Check event was added to queue
    assert not event_bus._queue.empty()
    event = event_bus._queue.get_nowait()
    assert event.payload.event_name == "config.reset_requested"


def test_event_emission_on_roi_rule_change(config_widget, event_bus):
    """Test that ROI rule change emits event to queue."""
    # Clear any events from widget initialization (BehavioralConfigWidget emits events)
    while not event_bus._queue.empty():
        event_bus._queue.get_nowait()

    # Change rule
    config_widget.roi_inclusion_rule_var.set("seg_overlap")
    config_widget._on_roi_rule_changed()

    # Check event was added to queue
    assert not event_bus._queue.empty()
    event = event_bus._queue.get_nowait()
    assert event.payload.event_name == "config.roi_rule_changed"
    assert event.payload.data["rule"] == "seg_overlap"


def test_invalid_input_handling(config_widget):
    """Test that invalid inputs raise ValueError when getting values."""
    config_widget.fps_var.set("invalid")

    with pytest.raises(ValueError):
        config_widget.get_values()


def test_partial_set_values(config_widget):
    """Test that set_values works with partial dict."""
    partial_values = {
        "video_processing": {
            "fps": 45,
        },
    }

    config_widget.set_values(partial_values)

    # Updated value
    assert config_widget.fps_var.get() == "45"

    # Unchanged values remain default
    assert config_widget.processing_interval_var.get() == "10"
    assert config_widget.window_length_var.get() == "7"


def test_widget_without_event_bus(tkinter_root):
    """Test that widget works without event bus."""
    widget = ConfigEditorWidget(tkinter_root, event_bus=None)
    widget.pack()
    tkinter_root.update()

    # Should not crash
    widget._on_save_clicked()
    widget._on_reset_clicked()
    widget._on_roi_rule_changed()

    # get_values should still work
    values = widget.get_values()
    assert "video_processing" in values
