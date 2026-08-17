"""Extended unit tests for ui/gui.py (Part 2)."""

from __future__ import annotations

from zebtrack.ui.gui import (
    PROJECT_STATUS_WIDGET_ORDER,
    STATUS_SYMBOLS,
    ApplicationGUI,
)


class TestGuiExtended2:
    """Test ApplicationGUI widget ordering and status symbols."""

    def test_project_status_widget_order_length(self):
        assert len(PROJECT_STATUS_WIDGET_ORDER) == 10
        assert PROJECT_STATUS_WIDGET_ORDER[0] == "total"
        assert PROJECT_STATUS_WIDGET_ORDER[-1] == "summary"

    def test_status_symbols_unicode(self):
        assert STATUS_SYMBOLS["arena"] == "\U0001f3df"
        assert STATUS_SYMBOLS["rois"] == "\U0001f3af"
        assert STATUS_SYMBOLS["trajectory"] == "\U0001f9ed"
        assert STATUS_SYMBOLS["summary"] == "\u03a3"

    def test_gui_dimensions_types(self):
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_WIDTH, int)
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_HEIGHT, int)
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH > 0
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT > 0

    def test_extract_setting_deeply_nested(self):
        class A:
            class B:
                class C:
                    val = 999

        assert ApplicationGUI._extract_setting(A, ("B", "C", "val"), 0) == 999
        assert ApplicationGUI._extract_setting(A, ("B", "missing", "val"), -1) == -1
