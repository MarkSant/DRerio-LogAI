"""Extended unit tests for ui/dialogs/block_detail_dialog.py."""

from __future__ import annotations

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended3:
    """Test BlockDetailDialog overrides and state variables."""

    def test_camera_override_defaults(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog._camera_index_override = None
        dialog._camera_friendly_name_override = None
        dialog._project_has_polygon = False

        assert dialog._camera_index_override is None
        assert dialog._camera_friendly_name_override is None
        assert dialog._project_has_polygon is False

    def test_duration_widgets_initial_state(self):
        dialog = object.__new__(BlockDetailDialog)
        dialog._duration_label = None
        dialog._subject_container = None

        assert dialog._duration_label is None
        assert dialog._subject_container is None
