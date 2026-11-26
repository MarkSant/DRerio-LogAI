"""Extended unit tests for ui/components/project_views/reports_tree_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_views.reports_tree_manager import (
    ReportsTreeManager,
    hierarchy_label,
)


class TestReportsTreeManagerExtended2:
    """Test ReportsTreeManager hierarchy labels, node types, and DI properties."""

    def test_hierarchy_label(self):
        assert hierarchy_label("group") in ("group", "grupo")
        assert hierarchy_label("day") in ("day", "dia")
        assert hierarchy_label("subject") in ("subject", "sujeito")
        assert hierarchy_label("unknown") in ("item", "item")

    def test_node_types_constants(self):
        assert "group" in ReportsTreeManager._HIERARCHY_NODE_TYPES
        assert "day" in ReportsTreeManager._HIERARCHY_NODE_TYPES
        assert "subject" in ReportsTreeManager._HIERARCHY_NODE_TYPES
        assert ReportsTreeManager._AQUARIUM_NODE_TYPE == "aquarium"

    def test_dialog_manager_property_injected_and_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        mock_dm = MagicMock()
        mgr_injected = ReportsTreeManager(gui, dialog_manager=mock_dm)
        assert mgr_injected.dialog_manager is mock_dm

        mgr_fallback = ReportsTreeManager(gui, dialog_manager=None)
        assert mgr_fallback.dialog_manager is gui.dialog_manager


class TestBarnesStrategyCorrectionWiring:
    """The right-click action: saves through the correction object and tells the user."""

    @staticmethod
    def _manager():
        gui = MagicMock()
        dialogs = MagicMock()
        manager = ReportsTreeManager(gui, dialog_manager=dialogs)
        manager._strategy_correction = MagicMock()
        return manager, dialogs

    def test_a_saved_correction_tells_the_user_to_regenerate(self):
        manager, dialogs = self._manager()
        manager._strategy_correction.apply.return_value = True
        manager._strategy_correction.regenerate_message.return_value = "Regenerate it"

        manager._handle_set_strategy("a.mp4", "serial")

        manager._strategy_correction.apply.assert_called_once_with("a.mp4", "serial")
        dialogs.show_info.assert_called_once_with("Search strategy", "Regenerate it")
        dialogs.show_error.assert_not_called()

    def test_a_failed_save_is_an_error_not_a_silent_success(self):
        manager, dialogs = self._manager()
        manager._strategy_correction.apply.return_value = False

        manager._handle_set_strategy("a.mp4", None)

        dialogs.show_error.assert_called_once()
        assert "left unchanged" in dialogs.show_error.call_args.args[1]
        dialogs.show_info.assert_not_called()
