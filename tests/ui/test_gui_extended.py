"""Extended unit tests for ui/gui.py."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zebtrack.ui.gui import (
    PROJECT_STATUS_WIDGET_ORDER,
    STATUS_SYMBOLS,
    ApplicationGUI,
    _panel_is_alive,
    _payload_get,
)


@dataclass
class DummyPayload:
    title: str

    count: int


class TestGuiExtended:
    def test_constants(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600

        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

        assert "total" in PROJECT_STATUS_WIDGET_ORDER
        assert "pending" in PROJECT_STATUS_WIDGET_ORDER
        assert "complete" in PROJECT_STATUS_WIDGET_ORDER
        assert "failed" in PROJECT_STATUS_WIDGET_ORDER

    def test_payload_get_dict(self):
        d = {"name": "test_exp", "val": 42}
        assert _payload_get(d, "name") == "test_exp"
        assert _payload_get(d, "val") == 42
        assert _payload_get(d, "missing", "default_val") == "default_val"

    def test_payload_get_dataclass(self):
        payload = DummyPayload(title="Alert", count=5)
        assert _payload_get(payload, "title") == "Alert"
        assert _payload_get(payload, "count") == 5
        assert _payload_get(payload, "nonexistent", "fallback") == "fallback"

    def test_payload_get_unsupported_types(self):
        assert _payload_get(None, "key", "default") == "default"
        assert _payload_get("string_payload", "key", 123) == 123
        assert _payload_get(42, "key", None) is None

    def test_extract_setting_nested(self):
        class Node:
            def __init__(self, child=None, val=None):
                self.child = child
                self.val = val

        root = Node(child=Node(val="target_value"))
        res = ApplicationGUI._extract_setting(root, ("child", "val"), "default")
        assert res == "target_value"

    def test_extract_setting_fallback(self):
        class Node:
            def __init__(self):
                self.other = 123

        root = Node()
        res = ApplicationGUI._extract_setting(root, ("missing", "path"), "fallback_value")
        assert res == "fallback_value"

        res_none = ApplicationGUI._extract_setting(None, ("any",), "fallback_value")
        assert res_none == "fallback_value"


class TestGuiExtended2:
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


class TestGuiExtended4:
    def test_update_button_state_buttons(self):
        gui = object.__new__(ApplicationGUI)
        gui.start_rec_btn = MagicMock()
        gui.stop_rec_btn = MagicMock()
        gui.process_video_btn = MagicMock()
        gui.analysis_display_widget = MagicMock()

        gui.update_button_state("start_rec", "disabled")
        gui.start_rec_btn.config.assert_called_once_with(state="disabled")

        gui.update_button_state("stop_rec", "normal")
        gui.stop_rec_btn.config.assert_called_once_with(state="normal")

        gui.update_button_state("process_video", "disabled")
        gui.process_video_btn.config.assert_called_once_with(state="disabled")

        gui.update_button_state("cancel_processing", "normal")
        gui.analysis_display_widget.enable_cancel_button.assert_called_once()

        gui.update_button_state("cancel_processing", "disabled")
        gui.analysis_display_widget.disable_cancel_button.assert_called_once()

    def test_hide_progress_bar(self):
        gui = object.__new__(ApplicationGUI)
        gui.analysis_display_widget = MagicMock()
        gui.hide_progress_bar()
        gui.analysis_display_widget.hide_progress.assert_called_once()

    @patch("zebtrack.ui.gui.messagebox.showinfo")
    def test_show_info_delegates(self, mock_info: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_info("Title", "Message")
        mock_info.assert_called_once_with("Title", "Message")

    @patch("zebtrack.ui.gui.messagebox.showwarning")
    def test_show_warning_delegates(self, mock_warn: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_warning("Warning Title", "Warning Message")
        mock_warn.assert_called_once_with("Warning Title", "Warning Message")

    @patch("zebtrack.ui.gui.messagebox.showerror")
    def test_show_error_delegates(self, mock_err: MagicMock):
        gui = object.__new__(ApplicationGUI)
        gui.show_error("Error Title", "Error Message")
        mock_err.assert_called_once_with("Error Title", "Error Message")


class TestGuiExtended5:
    def test_gui_default_canvas_dimensions(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600

    def test_gui_constant_types(self):
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_WIDTH, int)
        assert isinstance(ApplicationGUI.DEFAULT_CANVAS_HEIGHT, int)

    def test_gui_default_dimensions_positive(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH > 0
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT > 0


class TestGuiExtended6:
    def test_application_gui_canvas_constants(self):
        assert ApplicationGUI.DEFAULT_CANVAS_WIDTH == 800
        assert ApplicationGUI.DEFAULT_CANVAS_HEIGHT == 600


class TestPanelIsAlive:
    """Guards the rebind loop from panels whose widget tree is already gone.

    ``tab_builder`` destroys the tab and rebuilds it, so
    ``_rebind_project_manager`` can land on the previous instance. That used to
    raise ``TclError`` into a broad ``except`` and log a full traceback at
    WARNING for an ordinary project switch — indistinguishable from a real bug.
    """

    def test_live_widget_is_alive(self):
        panel = MagicMock()
        panel.is_alive.return_value = True

        assert _panel_is_alive(panel) is True

    def test_destroyed_widget_is_not_alive(self):
        panel = MagicMock()
        panel.is_alive.return_value = False

        assert _panel_is_alive(panel) is False

    def test_falls_back_to_winfo_exists(self):
        panel = SimpleNamespace(winfo_exists=lambda: 0)

        assert _panel_is_alive(panel) is False

    def test_object_without_widget_api_counts_as_alive(self):
        """Refusing to rebind a plain object would skip the very thing asked for."""
        assert _panel_is_alive(SimpleNamespace()) is True

    def test_raising_liveness_check_counts_as_dead(self):
        panel = SimpleNamespace()
        panel.is_alive = lambda: (_ for _ in ()).throw(RuntimeError("tk is gone"))

        assert _panel_is_alive(panel) is False
