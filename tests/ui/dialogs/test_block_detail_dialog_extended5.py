"""Extended unit tests for ui/dialogs/block_detail_dialog.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


class TestBlockDetailDialogExtended5:
    """Test BlockDetailDialog session startup, overrides, and coordinator invocation."""

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
