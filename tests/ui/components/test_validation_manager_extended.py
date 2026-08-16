"""Extended unit tests for ui/components/validation_manager.py."""

from __future__ import annotations

from collections import Counter
from typing import Any
from unittest.mock import MagicMock, patch

from zebtrack.ui.components.validation_manager import (
    STATUS_SYMBOLS,
    ValidationManager,
    project_status_meta,
)


class TestValidationManagerExtended:
    """Test ValidationManager configuration validations, dictionary deep merging,
    status metadata, and overview formatters.
    """

    def test_project_status_meta_contains_standard_keys(self):
        meta = project_status_meta()
        for key in ("pending", "processing", "processed", "complete", "failed"):
            assert key in meta
            icon, label = meta[key]
            assert isinstance(icon, str)
            assert isinstance(label, str)

    def test_status_symbols(self):
        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

    def test_deep_merge_dicts(self):
        base: dict[str, Any] = {
            "a": 1,
            "nested": {"x": 10, "y": 20},
            "list": [1, 2],
        }
        override: dict[str, Any] = {
            "a": 2,
            "nested": {"y": 30, "z": 40},
            "list": [3, 4],
            "new_key": "val",
        }
        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged["a"] == 2
        assert merged["nested"] == {"x": 10, "y": 30, "z": 40}
        assert merged["list"] == [3, 4]
        assert merged["new_key"] == "val"
        # Original base dict is untouched
        assert base["nested"]["y"] == 20

    def test_compose_overview_status_line(self):
        mock_gui = MagicMock()
        vm = ValidationManager(mock_gui)

        # Empty
        assert "No video" in vm.compose_overview_status_line(0, Counter())

        # With counts
        counts = Counter({"complete": 5, "failed": 1, "custom_status": 2})
        line = vm.compose_overview_status_line(8, counts)
        assert "8 video(s)" in line
        assert "5" in line
        assert "1" in line
        assert "+ 2" in line

    def test_save_global_config_from_widget_validation_errors(self):
        mock_gui = MagicMock()
        mock_dialogs = MagicMock()
        vm = ValidationManager(mock_gui, dialog_manager=mock_dialogs)

        # 1. Invalid FPS (<= 0)
        vm.save_global_config_from_widget(
            {
                "video_processing": {
                    "fps": 0,
                    "processing_interval": 1,
                    "display_interval": 1,
                    "processing_offset": 0,
                },
                "recorder": {"flush_interval_seconds": 1, "flush_row_threshold": 10},
                "trajectory_smoothing": {"window_length": 5, "polyorder": 2},
            }
        )
        mock_dialogs.show_error.assert_called_once()
        assert "FPS must be greater than 0" in mock_dialogs.show_error.call_args[0][1]
        mock_dialogs.show_error.reset_mock()

        # 2. Invalid window_length (even number)
        vm.save_global_config_from_widget(
            {
                "video_processing": {
                    "fps": 30,
                    "processing_interval": 1,
                    "display_interval": 1,
                    "processing_offset": 0,
                },
                "recorder": {"flush_interval_seconds": 1, "flush_row_threshold": 10},
                "trajectory_smoothing": {"window_length": 4, "polyorder": 2},
            }
        )
        mock_dialogs.show_error.assert_called_once()
        assert "Window length must be odd" in mock_dialogs.show_error.call_args[0][1]

    def test_check_live_project_calibration_skips_non_live(self):
        mock_gui = MagicMock()
        mock_gui.controller.project_manager.get_project_type.return_value = "video"
        mock_dialogs = MagicMock()

        vm = ValidationManager(mock_gui, dialog_manager=mock_dialogs)
        vm.check_live_project_calibration()

        mock_dialogs.ask_ok_cancel.assert_not_called()

    def test_check_live_project_calibration_prompts_when_no_zones(self):
        mock_gui = MagicMock()
        mock_gui.controller.project_manager.get_project_type.return_value = "live"
        mock_dialogs = MagicMock()
        mock_dialogs.ask_ok_cancel.return_value = True

        vm = ValidationManager(mock_gui, dialog_manager=mock_dialogs)
        with patch.object(vm, "get_zone_data_for_active_context", return_value=None):
            vm.check_live_project_calibration()

        mock_dialogs.ask_ok_cancel.assert_called_once()
        mock_dialogs.show_info.assert_called_once()
