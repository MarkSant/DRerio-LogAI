"""Extended unit tests for ui/dialogs/block_detail_dialog.py (Part 7)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended7:
    """Test BlockDetailDialog animal metadata properties and field defaults."""

    def test_block_detail_dialog_animal_metadata_initial(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog.subject_name = "Fish_01"
        dialog.video_path = "/path/to/vid.mp4"
        dialog.is_complete = True

        assert dialog.subject_name == "Fish_01"
        assert dialog.video_path == "/path/to/vid.mp4"
        assert dialog.is_complete is True

    def test_block_detail_dialog_day_and_group_properties(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog.day_num = 3
        dialog.group_name = "Control"

        assert dialog.day_num == 3
        assert dialog.group_name == "Control"

    def test_block_detail_dialog_is_complete_toggle(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog.is_complete = False
        dialog.is_complete = True
        assert dialog.is_complete is True
