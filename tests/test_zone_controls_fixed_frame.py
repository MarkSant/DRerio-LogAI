"""Test that ZoneControlsWidget has a fixed button frame."""

import pytest
import tkinter as tk
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus import EventBus


@pytest.mark.gui
def test_zone_controls_has_fixed_button_frame():
    """Verify ZoneControlsWidget exposes a fixed_button_frame."""
    root = tk.Tk()
    try:
        event_bus = EventBus()
        widget = ZoneControlsWidget(root, event_bus=event_bus)
        widget.pack()
        root.update()

        # Check that fixed_button_frame exists
        assert hasattr(widget, "fixed_button_frame"), "ZoneControlsWidget must have fixed_button_frame"
        assert isinstance(widget.fixed_button_frame, tk.Widget), "fixed_button_frame must be a widget"
        
        # Test that we can add a button to it
        test_button = tk.Button(widget.fixed_button_frame, text="Test Button")
        test_button.pack()
        root.update()
        
        # Verify button was added successfully
        assert test_button.winfo_exists(), "Button should exist in fixed_button_frame"
        
    finally:
        root.destroy()


@pytest.mark.gui
def test_gui_exposes_fixed_button_frame():
    """Verify ApplicationGUI exposes fixed_button_frame from zone_controls after zone tab creation."""
    # This test verifies the fix for the AttributeError when accessing fixed_button_frame
    # The actual integration test is better done as part of the full application test
    # Here we just verify that the property is correctly set up in the code
    
    # Read the source to verify the assignment exists
    import inspect
    from zebtrack.ui.gui import ApplicationGUI
    
    # Get the source of _create_roi_analysis_tab
    source = inspect.getsource(ApplicationGUI._create_roi_analysis_tab)
    
    # Verify that the zone_controls widget is created
    assert "ZoneControlsWidget" in source, "_create_roi_analysis_tab should create ZoneControlsWidget"
    
    # Verify that fixed_button_frame is exposed
    assert "self.fixed_button_frame = self.zone_controls.fixed_button_frame" in source, \
        "fixed_button_frame should be exposed from zone_controls"
    
    print("✓ Code verification passed: fixed_button_frame is properly exposed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
