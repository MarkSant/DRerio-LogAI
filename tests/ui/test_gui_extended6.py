"""Extended unit tests for ui/gui.py (Part 6)."""

from __future__ import annotations

from zebtrack.ui.gui import ApplicationGUI


class TestGuiExtended6:
    """Test ApplicationGUI canvas constants, aliases, and attribute initializations."""

    def test_application_gui_canvas_constants(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600
