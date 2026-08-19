"""Extended unit tests for ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.dialogs.block_detail_dialog import (
    BlockDetailDialog,
    _block_label,
)


class TestBlockDetailDialogHelpers:
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


class TestBlockDetailDialogExtended2:
    def test_subjects_enumeration(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.subjects_per_group = 4

        subjects = dialog._subjects()
        assert subjects == ["1", "2", "3", "4"]

    def test_subjects_enumeration_zero(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.subjects_per_group = 0

        subjects = dialog._subjects()
        assert subjects == []


class TestBlockDetailDialogExtended4:
    def test_subjects_enumeration_from_count(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.subjects_per_group = 4
        assert dialog._subjects() == ["1", "2", "3", "4"]

    def test_subjects_enumeration_zero(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.subjects_per_group = 0
        assert dialog._subjects() == []

    def test_subjects_enumeration_single(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.subjects_per_group = 1
        assert dialog._subjects() == ["1"]


class TestBlockDetailDialogExtended5:
    def test_start_session_delegates_to_coordinator(self, monkeypatch: pytest.MonkeyPatch):
        dialog = object.__new__(BlockDetailDialog)
        dialog.day_num = 1
        dialog.group_name = "Control"
        dialog._camera_index_override = 2
        dialog._camera_friendly_name_override = "USB Cam 2"
        monkeypatch.setattr(dialog, "_project_data", lambda: {})
        mock_destroy = MagicMock()
        monkeypatch.setattr(dialog, "destroy", mock_destroy)
        dialog.session_coordinator = MagicMock()
        dialog.session_coordinator.start_live_project_session.return_value = True

        dialog.start_session("1")
        mock_destroy.assert_called_once()
        dialog.session_coordinator.start_live_project_session.assert_called_once_with(
            day=1,
            group="Control",
            subject="1",
            duration_s=pytest.approx(300.0),
            camera_index_override=2,
            camera_friendly_name_override="USB Cam 2",
        )
