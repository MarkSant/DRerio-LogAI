"""Extended unit tests for StateSynchronizer in ui/components/state_synchronizer.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.state_manager import StateCategory, StateManager
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


class TestStateSynchronizerExtended:
    """Test StateSynchronizer initialization, subscriptions, and dialog manager resolution."""

    def test_initialization_with_injected_dependencies(self):
        gui_mock = MagicMock()
        dialog_mgr = MagicMock()
        state_mgr = StateManager()

        sync = StateSynchronizer(
            gui=gui_mock,
            dialog_manager=dialog_mgr,
            state_manager=state_mgr,
        )

        assert sync.gui is gui_mock
        assert sync.dialog_manager is dialog_mgr
        assert sync._state_manager is state_mgr

    def test_dialog_manager_fallback(self):
        gui_mock = MagicMock()
        gui_mock.dialog_manager = MagicMock()

        sync = StateSynchronizer(gui=gui_mock)
        assert sync.dialog_manager is gui_mock.dialog_manager

    def test_subscribe_to_state_changes(self):
        gui_mock = MagicMock()
        state_mgr = MagicMock()

        sync = StateSynchronizer(
            gui=gui_mock,
            state_manager=state_mgr,
        )

        sync.subscribe_to_state_changes()

        assert state_mgr.subscribe.call_count == 4
        # Verify subscribed categories
        categories = [call[0][0] for call in state_mgr.subscribe.call_args_list]
        assert StateCategory.RECORDING in categories
        assert StateCategory.PROCESSING in categories
        assert StateCategory.DETECTOR in categories
        assert StateCategory.PROJECT in categories
