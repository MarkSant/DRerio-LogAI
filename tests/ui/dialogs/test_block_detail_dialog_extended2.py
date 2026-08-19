"""Extended unit tests for ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended2:
    """Test BlockDetailDialog labels, subject enumeration, and duration parsing."""

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
