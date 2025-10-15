"""
Tests for UI component widgets.

These tests verify that the new modular UI components can be instantiated,
configured, and emit events correctly without depending on the full ApplicationGUI.

KNOWN ISSUE: When run as part of the full test suite (pytest -q), these tests may fail
with "_tkinter.TclError: can't invoke 'tk' command: application has been destroyed" due
to ttkbootstrap Style singleton maintaining stale references to Tk instances from previous
test modules. This is a limitation of the ttkbootstrap library's singleton pattern.

WORKAROUND: Run this test module in isolation: pytest tests/ui/test_components.py
When run in isolation, all 22 tests pass successfully.

See: https://github.com/israel-dryer/ttkbootstrap/issues (Style singleton cleanup)
"""

import tkinter as tk
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components import (
    AnalysisControlsWidget,
    BaseWidget,
    ControlPanelWidget,
    ProjectOverviewWidget,
    VideoDisplayWidget,
    ZoneControlsWidget,
)
from zebtrack.ui.event_bus import EventBus, NamedEvent


@pytest.fixture(scope="module")
def root():
    """Create a single Tkinter root window shared by all tests in this module.

    Using module scope prevents ttkbootstrap Style singleton issues that occur
    when creating/destroying multiple Tk instances in rapid succession. The Style
    singleton Publisher maintains widget references that become stale when Tk is
    destroyed between tests, causing "application has been destroyed" errors.

    Trade-off: Tests share the same Tk instance, so they must clean up after
    themselves by destroying any widgets they create. This is acceptable since
    these are unit tests for individual widgets, not integration tests.
    """
    root = tk.Tk()
    root.withdraw()  # Hide window during tests

    yield root

    # Final cleanup after all tests complete
    try:
        for widget in list(root.winfo_children()):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def event_bus():
    """Create a mock event bus."""
    bus = MagicMock(spec=EventBus)
    return bus


class TestBaseWidget:
    """Tests for the BaseWidget base class."""

    def test_base_widget_requires_build_ui_implementation(self, root):
        """BaseWidget should raise NotImplementedError if _build_ui is not implemented."""
        with pytest.raises(NotImplementedError, match="must implement _build_ui"):
            BaseWidget(root)

    def test_base_widget_emit_event_without_bus(self, root):
        """BaseWidget should handle emit_event gracefully when no event bus is configured."""

        class TestWidget(BaseWidget):
            def _build_ui(self):
                pass

        widget = TestWidget(root)
        # Should not raise an error
        widget.emit_event("test.event", {"data": "value"})

    def test_base_widget_emit_event_with_bus(self, root, event_bus):
        """BaseWidget should emit events to the event bus."""

        class TestWidget(BaseWidget):
            def _build_ui(self):
                pass

        widget = TestWidget(root, event_bus=event_bus)
        widget.emit_event("test.event", {"data": "value"})

        # Verify event was published
        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0][0]
        assert isinstance(call_args, NamedEvent)
        assert call_args.event_name == "test.event"
        assert call_args.data == {"data": "value"}

    def test_base_widget_set_enabled(self, root):
        """BaseWidget should enable/disable all child widgets."""

        class TestWidget(BaseWidget):
            def _build_ui(self):
                self.button = tk.Button(self, text="Test")
                self.button.pack()

        widget = TestWidget(root)

        # Disable widget
        widget.set_enabled(False)
        assert widget.button["state"] == "disabled"

        # Enable widget
        widget.set_enabled(True)
        assert widget.button["state"] == "normal"


class TestVideoDisplayWidget:
    """Tests for the VideoDisplayWidget."""

    def test_video_display_widget_creates_canvas(self, root):
        """VideoDisplayWidget should create a canvas."""
        widget = VideoDisplayWidget(root)
        assert widget.canvas is not None
        assert isinstance(widget.canvas, tk.Canvas)

    def test_video_display_widget_custom_dimensions(self, root):
        """VideoDisplayWidget should accept custom dimensions."""
        widget = VideoDisplayWidget(root, width=640, height=480)
        assert widget._canvas_width == 640
        assert widget._canvas_height == 480

    def test_video_display_widget_clear(self, root):
        """VideoDisplayWidget clear should reset image state."""
        widget = VideoDisplayWidget(root)
        widget._original_image = MagicMock()
        widget._raw_bg_image = MagicMock()

        widget.clear()

        assert widget._original_image is None
        assert widget._raw_bg_image is None

    def test_video_display_widget_coordinate_conversion(self, root):
        """VideoDisplayWidget should convert coordinates correctly."""
        widget = VideoDisplayWidget(root)

        # Set up known scale and offset
        widget._bg_scale = 0.5
        widget._bg_offset = (100, 50)

        # Test video to canvas
        canvas_x, canvas_y = widget.video_to_canvas(200, 100)
        assert canvas_x == 200 * 0.5 + 100  # 200
        assert canvas_y == 100 * 0.5 + 50  # 100

        # Test canvas to video (reverse)
        video_x, video_y = widget.canvas_to_video(200, 100)
        assert video_x == (200 - 100) / 0.5  # 200
        assert video_y == (100 - 50) / 0.5  # 100


class TestZoneControlsWidget:
    """Tests for the ZoneControlsWidget."""

    def test_zone_controls_widget_creates_ui_elements(self, root):
        """ZoneControlsWidget should create all expected UI elements."""
        widget = ZoneControlsWidget(root)

        # Check key widgets exist
        assert widget.draw_roi_button is not None
        assert widget.zone_listbox is not None
        assert widget.video_selector_tree is not None
        assert widget.roi_template_combobox is not None

    def test_zone_controls_widget_emits_auto_detect_event(self, root, event_bus):
        """ZoneControlsWidget should emit event when auto-detect is clicked."""
        widget = ZoneControlsWidget(root, event_bus=event_bus)
        widget.stabilization_frames_var.set("20")

        widget._on_auto_detect_clicked()

        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0][0]
        assert call_args.event_name == "zone.auto_detect_clicked"
        assert call_args.data["stabilization_frames"] == 20

    def test_zone_controls_widget_set_draw_roi_enabled(self, root):
        """ZoneControlsWidget should enable/disable ROI draw button."""
        widget = ZoneControlsWidget(root)

        widget.set_draw_roi_enabled(True)
        assert str(widget.draw_roi_button["state"]) == "normal"

        widget.set_draw_roi_enabled(False)
        assert str(widget.draw_roi_button["state"]) == "disabled"

    def test_zone_controls_widget_update_template_list(self, root):
        """ZoneControlsWidget should update template combobox."""
        widget = ZoneControlsWidget(root)

        templates = ["Template 1", "Template 2", "Template 3"]
        widget.update_template_list(templates)

        assert widget.roi_template_combobox["values"] == tuple(templates)


class TestControlPanelWidget:
    """Tests for the ControlPanelWidget."""

    def test_control_panel_widget_creates_buttons(self, root):
        """ControlPanelWidget should create start/stop buttons."""
        widget = ControlPanelWidget(root)

        assert widget.start_rec_btn is not None
        assert widget.stop_rec_btn is not None
        assert widget.process_video_btn is not None

    def test_control_panel_widget_emits_start_recording_event(self, root, event_bus):
        """ControlPanelWidget should emit event when start recording is clicked."""
        widget = ControlPanelWidget(root, event_bus=event_bus)

        widget._on_start_recording_clicked()

        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0][0]
        assert call_args.event_name == "control.start_recording"

    def test_control_panel_widget_set_recording_state(self, root):
        """ControlPanelWidget should update button states based on recording state."""
        widget = ControlPanelWidget(root)

        # When recording
        widget.set_recording_state(True)
        assert widget.start_rec_btn["state"] == "disabled"
        assert widget.stop_rec_btn["state"] == "normal"

        # When not recording
        widget.set_recording_state(False)
        assert widget.start_rec_btn["state"] == "normal"
        assert widget.stop_rec_btn["state"] == "disabled"


class TestProjectOverviewWidget:
    """Tests for the ProjectOverviewWidget."""

    def test_project_overview_widget_creates_tree_and_cards(self, root):
        """ProjectOverviewWidget should create status cards and tree."""
        widget = ProjectOverviewWidget(root)

        assert widget.project_overview_tree is not None
        assert widget.status_cards_frame is not None
        assert len(widget.project_status_vars) > 0

    def test_project_overview_widget_update_status_counts(self, root):
        """ProjectOverviewWidget should update status card counts."""
        widget = ProjectOverviewWidget(root)

        counts = {"total": 10, "pending": 3, "processed": 5, "complete": 2}

        widget.update_status_counts(counts)

        assert widget.project_status_vars["total"].get() == "10"
        assert widget.project_status_vars["pending"].get() == "3"
        assert widget.project_status_vars["processed"].get() == "5"
        assert widget.project_status_vars["complete"].get() == "2"

    def test_project_overview_widget_emits_refresh_event(self, root, event_bus):
        """ProjectOverviewWidget should emit event when refresh is clicked."""
        widget = ProjectOverviewWidget(root, event_bus=event_bus)

        widget._on_refresh_clicked()

        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0][0]
        assert call_args.event_name == "project.refresh_requested"


class TestAnalysisControlsWidget:
    """Tests for the AnalysisControlsWidget."""

    def test_analysis_controls_widget_creates_ui_elements(self, root):
        """AnalysisControlsWidget should create all expected UI elements."""
        widget = AnalysisControlsWidget(root)

        assert widget.analysis_status_label is not None
        assert widget.track_selector_widget is not None
        assert widget.analysis_video_label is not None

    def test_analysis_controls_widget_set_metadata(self, root):
        """AnalysisControlsWidget should update metadata display."""
        widget = AnalysisControlsWidget(root)

        widget.set_metadata("Group A", "Day 1", "Subject 01", "Test Task")

        assert "Group A" in widget.analysis_group_var.get()
        assert "Day 1" in widget.analysis_day_var.get()
        assert "Subject 01" in widget.analysis_subject_var.get()
        assert "Test Task" in widget.analysis_task_var.get()

    def test_analysis_controls_widget_update_track_options(self, root):
        """AnalysisControlsWidget should update track selector options."""
        widget = AnalysisControlsWidget(root)

        tracks = ["Todos", "1", "2", "3"]
        widget.update_track_options(tracks)

        assert widget.track_selector_widget["values"] == tuple(tracks)

    def test_analysis_controls_widget_emits_track_selected_event(self, root, event_bus):
        """AnalysisControlsWidget should emit event when track is selected."""
        widget = AnalysisControlsWidget(root, event_bus=event_bus)
        widget.track_selector_var.set("1")

        widget._on_track_selection_changed(None)

        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0][0]
        assert call_args.event_name == "analysis.track_selected"
        assert call_args.data["track_id"] == "1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
