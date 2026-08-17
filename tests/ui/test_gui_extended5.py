"""Extended unit tests for ui/gui.py (Part 5)."""

from __future__ import annotations

from zebtrack.ui.gui import ApplicationGUI


class TestGuiExtended5:
    """Test ApplicationGUI constants and default dimensions."""

    def test_gui_default_canvas_dimensions(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600

    def test_gui_constant_types(self):
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_WIDTH, int)
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_HEIGHT, int)

    def test_gui_default_dimensions_positive(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH > 0
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT > 0
