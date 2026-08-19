"""Extended unit tests for ui/dialogs/block_detail_dialog.py (Part 4)."""

from __future__ import annotations

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended4:
    """Test BlockDetailDialog subject enumerations and helper methods."""

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
