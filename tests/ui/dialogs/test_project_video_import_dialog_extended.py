"""Extended unit tests for ui/dialogs/project_video_import_dialog.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.dialogs.project_video_import_dialog import (
    SubjectEntriesDialog,
    VideoMetadataDialog,
)


class TestProjectVideoImportDialogExtended:
    """Test SubjectEntriesDialog and VideoMetadataDialog validation and apply logic."""

    def test_coerce_day(self):
        assert SubjectEntriesDialog._coerce_day(5, fallback=1) == 5
        assert SubjectEntriesDialog._coerce_day("3", fallback=1) == 3
        assert SubjectEntriesDialog._coerce_day(0, fallback=2) == 2
        assert SubjectEntriesDialog._coerce_day(-1, fallback=2) == 2
        assert SubjectEntriesDialog._coerce_day("invalid", fallback=1) == 1
        assert SubjectEntriesDialog._coerce_day(None, fallback=4) == 4

    def test_subject_entries_dialog_apply(self):
        dialog = object.__new__(SubjectEntriesDialog)
        mock_g1 = MagicMock()
        mock_g1.get.return_value = "Control"
        mock_d1 = MagicMock()
        mock_d1.get.return_value = 1
        mock_s1 = MagicMock()
        mock_s1.get.return_value = "Animal_1"

        dialog._rows = [(mock_g1, mock_d1, mock_s1)]
        dialog.apply()

        assert dialog.result is not None
        assert len(dialog.result) == 1
        assert dialog.result[0] == {
            "group": "Control",
            "day": 1,
            "subject": "Animal_1",
        }

    def test_video_metadata_dialog_apply_single(self):
        dialog = object.__new__(VideoMetadataDialog)
        dialog.group_var = MagicMock()
        dialog.group_var.get.return_value = "Treated"
        dialog.day_var = MagicMock()
        dialog.day_var.get.return_value = 2
        dialog.subject_var = MagicMock()
        dialog.subject_var.get.return_value = "Sub_A"
        dialog.subject_entries = []

        dialog.apply()
        assert dialog.result is not None
        assert dialog.result["group"] == "Treated"
        assert dialog.result["day"] == 2
        assert dialog.result["subject"] == "Sub_A"

    def test_video_metadata_dialog_apply_multiple_entries(self):
        dialog = object.__new__(VideoMetadataDialog)
        dialog.group_var = MagicMock()
        dialog.group_var.get.return_value = "Treated"
        dialog.day_var = MagicMock()
        dialog.day_var.get.return_value = 2
        dialog.subject_entries = [
            {"group": "Treated", "day": 2, "subject": "Sub_1"},
            {"group": "Treated", "day": 2, "subject": "Sub_2"},
        ]

        dialog.apply()
        assert dialog.result is not None
        assert "subject_entries" in dialog.result
        assert len(dialog.result["subject_entries"]) == 2
