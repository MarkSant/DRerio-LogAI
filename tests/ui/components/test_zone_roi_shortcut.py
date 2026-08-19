"""ZONE_OPEN_ROI_SETTINGS: the Zone tab's shortcut into the single ROI editor.

The Zone tab used to carry a SECOND editor for the ROI inclusion rule, writing
the same ``project_data["roi_settings"]`` as the Advanced Settings tab but
omitting ``roi_bbox_overlap_basis`` (leaving its "Min. overlap" denominator
ambiguous) and the ``persist_masks`` prerequisite that ``seg_overlap`` needs.
It now shows a read-only summary and routes here.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import UIEvents


def _dispatcher_handler(gui):
    """Register EventDispatcher's zone handlers and return the shortcut one."""
    from zebtrack.ui.components.event_dispatcher import EventDispatcher

    event_bus = MagicMock()
    subscriptions: dict = {}
    event_bus.subscribe.side_effect = lambda evt, fn: subscriptions.setdefault(evt, fn)

    gui.event_bus = event_bus
    dispatcher = EventDispatcher(gui)
    dispatcher.subscribe_zone_component_events()
    return subscriptions[UIEvents.ZONE_OPEN_ROI_SETTINGS]


class TestShortcutHandler:
    def test_selects_the_advanced_settings_tab_and_focuses_roi(self):
        widget = MagicMock()
        notebook = MagicMock()
        gui = SimpleNamespace(
            config_editor_widget=widget,
            notebook=notebook,
            set_status=MagicMock(),
        )

        _dispatcher_handler(gui)(None)

        notebook.select.assert_called_once_with(widget)
        widget.focus_roi_section.assert_called_once()

    def test_reports_when_the_tab_is_not_built(self):
        """A live project can reach the Zone tab before the analysis widgets mount.

        Clicking a button that silently does nothing is the failure mode this
        whole PR is about -- say so instead.
        """
        gui = SimpleNamespace(
            config_editor_widget=None,
            notebook=MagicMock(),
            set_status=MagicMock(),
        )

        _dispatcher_handler(gui)(None)

        gui.set_status.assert_called_once()
        gui.notebook.select.assert_not_called()

    def test_tab_not_attached_degrades_to_a_status_message(self):
        from tkinter import TclError

        widget = MagicMock()
        notebook = MagicMock()
        notebook.select.side_effect = TclError("not managed by this notebook")
        gui = SimpleNamespace(
            config_editor_widget=widget,
            notebook=notebook,
            set_status=MagicMock(),
        )

        _dispatcher_handler(gui)(None)

        gui.set_status.assert_called_once()
        widget.focus_roi_section.assert_not_called()


def _is_packed(widget) -> bool:
    """True when the widget is currently managed by a geometry manager.

    ``winfo_ismapped()`` is useless here: nothing is gridded into a visible
    toplevel in tests, so every widget reports unmapped. The geometry manager
    reflects pack()/pack_forget() exactly.
    """
    return bool(widget.winfo_manager())


@pytest.mark.gui
class TestClosePolygonButtonGating:
    """ "Close Polygon" only means something while drawing freehand.

    Every caller of ``show_interactive_buttons`` today is a vertex-editing
    entry point, so the button was visible only where it cannot work. It is
    hidden there rather than greyed out -- a permanently disabled control is
    still clutter.
    """

    def test_hidden_when_editing_existing_vertices(self, tkinter_root):
        widget = ZoneControlsWidget(tkinter_root, event_bus=MagicMock())
        tkinter_root.update_idletasks()

        widget.show_interactive_buttons()  # default: vertex editing

        assert not _is_packed(widget.finish_drawing_btn)
        # The two controls that DO act here stay visible.
        assert _is_packed(widget.save_arena_btn)
        assert _is_packed(widget.discard_arena_btn)

    def test_shown_for_a_freehand_drawing_session(self, tkinter_root):
        widget = ZoneControlsWidget(tkinter_root, event_bus=MagicMock())
        tkinter_root.update_idletasks()

        widget.show_interactive_buttons(freehand_drawing=True)

        assert _is_packed(widget.finish_drawing_btn)
        assert str(widget.finish_drawing_btn.cget("state")) == "normal"

    def test_reappears_left_of_save_after_an_editing_session(self, tkinter_root):
        """Workflow order must survive the hide/show cycle.

        A bare ``pack()`` on the way back would append the button to the RIGHT
        of Discard, silently reordering the strip.
        """
        widget = ZoneControlsWidget(tkinter_root, event_bus=MagicMock())
        tkinter_root.update_idletasks()

        widget.show_interactive_buttons()  # hides it
        widget.show_interactive_buttons(freehand_drawing=True)  # brings it back
        tkinter_root.update_idletasks()

        frame = widget.interactive_buttons_frame
        close_polygon = widget.finish_drawing_btn
        save = widget.save_arena_btn
        discard = widget.discard_arena_btn
        assert frame is not None
        assert close_polygon is not None and save is not None and discard is not None

        packed = list(frame.pack_slaves())
        assert packed.index(close_polygon) < packed.index(save)
        assert packed.index(save) < packed.index(discard)

    def test_discard_button_is_packed_exactly_once(self, tkinter_root):
        """It used to be packed twice, silently re-ordering the strip."""
        widget = ZoneControlsWidget(tkinter_root, event_bus=MagicMock())
        tkinter_root.update_idletasks()

        frame = widget.interactive_buttons_frame
        discard = widget.discard_arena_btn
        save = widget.save_arena_btn
        assert frame is not None
        assert discard is not None and save is not None

        packed = list(frame.pack_slaves())
        assert packed.count(discard) == 1
        assert packed.index(save) < packed.index(discard)
