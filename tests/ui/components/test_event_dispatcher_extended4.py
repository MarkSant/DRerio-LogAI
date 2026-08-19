"""Extended unit tests for ui/components/event_dispatcher.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.event_dispatcher import EventDispatcher


class TestEventDispatcherExtended4:
    """Test EventDispatcher context detection, modes, and require_gui guard."""

    def test_context_detection_gui(self):
        gui = MagicMock()
        gui.event_bus = MagicMock()
        del gui.subscribe  # ensure it's treated as gui

        dispatcher = EventDispatcher(gui)
        assert dispatcher.gui is gui
        assert dispatcher.event_bus is gui.event_bus

    def test_context_detection_event_bus(self):
        eb = MagicMock()
        eb.subscribe = MagicMock()

        dispatcher = EventDispatcher(eb)
        assert dispatcher.gui is None
        assert dispatcher.event_bus is eb

    def test_require_gui_guard(self):
        dispatcher = EventDispatcher(None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI"):
            dispatcher._require_gui()
