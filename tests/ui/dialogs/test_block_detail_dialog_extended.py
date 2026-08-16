"""Extended unit tests for ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.ui.dialogs.block_detail_dialog import (
    BlockDetailDialog,
    _block_label,
)


class TestBlockDetailDialogHelpers:
    """Test BlockDetailDialog helper functions and initialization."""

    def test_block_label_formatting(self):
        label = _block_label(1, "Control")
        assert "1" in label
        assert "Control" in label

    def test_block_label_with_different_inputs(self):
        label2 = _block_label(5, "Treated")
        assert "5" in label2
        assert "Treated" in label2

    @patch("zebtrack.ui.dialogs.block_detail_dialog.BlockDetailDialog.build_ui")
    def test_block_detail_dialog_init_int_day(self, mock_build_ui, tkinter_root):
        mock_pm = MagicMock()
        mock_pm.project_data = {"subjects_per_group": 5}
        mock_pm.get_completed_sessions.return_value = []
        mock_pm.get_zone_data.return_value = None
        mock_pm.project_path = "/path/project"

        dlg = BlockDetailDialog(
            parent=tkinter_root,
            day=1,
            group="Control",
            project_manager=mock_pm,
            session_coordinator=MagicMock(),
            live_batch_coordinator=MagicMock(),
        )

        assert dlg.day_num == 1
        assert dlg.day == "Dia_1"
        assert dlg.group_name == "Control"
        assert dlg.subjects_per_group == 5
        mock_build_ui.assert_called_once()
        dlg.destroy()

    @patch("zebtrack.ui.dialogs.block_detail_dialog.BlockDetailDialog.build_ui")
    def test_block_detail_dialog_init_str_day(self, mock_build_ui, tkinter_root):
        mock_pm = MagicMock()
        mock_pm.project_data = {"subjects_per_group": 8}
        mock_pm.get_completed_sessions.return_value = [(2, "TestGroup", 1)]
        mock_pm.get_zone_data.return_value = MagicMock(polygon=[(0, 0), (1, 1)])
        mock_pm.project_path = "/path/project"

        dlg = BlockDetailDialog(
            parent=tkinter_root,
            day="Dia_2",
            group="TestGroup",
            project_manager=mock_pm,
            session_coordinator=MagicMock(),
            live_batch_coordinator=MagicMock(),
        )

        assert dlg.day_num == 2
        assert dlg.day == "Dia_2"
        assert dlg._project_has_polygon is True
        assert (2, "TestGroup", 1) in dlg.completed_sessions
        dlg.destroy()
