"""Extended unit tests for ui/components/state_synchronizer.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended7:
    """Test StateSynchronizer dependency injection, fallback, and state manager access."""

    def test_state_synchronizer_init(self):
        gui = MagicMock()
        dialog_mgr = MagicMock()
        state_mgr = MagicMock()

        sync = StateSynchronizer(
            gui,
            dialog_manager=dialog_mgr,
            state_manager=state_mgr,
        )

        assert sync.gui is gui
        assert sync.dialog_manager is dialog_mgr
        assert sync._state_manager is state_mgr

    def test_state_synchronizer_dialog_manager_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        sync = StateSynchronizer(gui)
        assert sync.dialog_manager is gui.dialog_manager

    def test_state_synchronizer_gui_reference(self):
        gui = MagicMock()
        sync = StateSynchronizer(gui)
        assert sync.gui is gui
