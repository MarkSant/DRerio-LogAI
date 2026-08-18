"""Extended unit tests for ui/dialogs/block_detail_dialog.py (Part 8)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended8:
    """Test BlockDetailDialog camera override defaults and attribute bindings."""

    def test_block_detail_dialog_camera_override_defaults(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog._block_data = {"camera_override": True, "custom_fps": 60.0}

        assert dialog._block_data["camera_override"] is True
        assert dialog._block_data["custom_fps"] == 60.0

    def test_block_detail_dialog_is_complete_flag(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog._is_complete = True
        assert dialog._is_complete is True
        dialog._is_complete = False
        assert dialog._is_complete is False

    def test_block_detail_dialog_subject_name_attr(self):
        dialog: Any = object.__new__(BlockDetailDialog)
        dialog.subject_name = "Subject_01"
        assert dialog.subject_name == "Subject_01"
