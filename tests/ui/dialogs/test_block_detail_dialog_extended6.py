"""Extended unit tests for ui/dialogs/block_detail_dialog.py (Part 6)."""

from __future__ import annotations

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended6:
    """Test BlockDetailDialog camera override defaults and attribute properties."""

    def test_block_detail_dialog_camera_overrides_initial(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog._camera_index_override = None
        dialog._camera_friendly_name_override = None
        dialog._duration_label = None
        dialog._subject_container = None

        assert dialog._camera_index_override is None
        assert dialog._camera_friendly_name_override is None
        assert dialog._duration_label is None
        assert dialog._subject_container is None

    def test_block_detail_dialog_camera_overrides_set(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog._camera_index_override = 1
        dialog._camera_friendly_name_override = "Webcam 1"

        assert dialog._camera_index_override == 1
        assert dialog._camera_friendly_name_override == "Webcam 1"

    def test_block_detail_dialog_day_and_group(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog.day_num = 2
        dialog.group_name = "Treated"

        assert dialog.day_num == 2
        assert dialog.group_name == "Treated"
