"""Extended unit tests for ui/components/validation_manager.py (Part 5)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import ValidationManager


class TestValidationManagerExtended5:
    """Test ValidationManager configuration interval, threshold validations, and deep merging."""

    def test_save_global_config_invalid_processing_interval(self):
        gui = MagicMock()
        vm = ValidationManager(gui)
        gui.dialog_manager = MagicMock()

        values = {
            "video_processing": {
                "fps": 30.0,
                "processing_interval": 0,
                "display_interval": 1,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 10.0,
                "flush_row_threshold": 100,
            },
            "trajectory_smoothing": {
                "window_length": 5,
                "polyorder": 2,
            },
        }

        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()
        assert "processing interval" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_save_global_config_invalid_flush_rows(self):
        gui = MagicMock()
        vm = ValidationManager(gui)
        gui.dialog_manager = MagicMock()

        values = {
            "video_processing": {
                "fps": 30.0,
                "processing_interval": 1,
                "display_interval": 1,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 10.0,
                "flush_row_threshold": 0,  # Invalid: must be >= 1
            },
            "trajectory_smoothing": {
                "window_length": 5,
                "polyorder": 2,
            },
        }

        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()
        assert "flush" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_deep_merge_dicts_empty(self):
        base = {"a": 1, "b": {"c": 2}}
        override: dict[str, Any] = {}
        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged == {"a": 1, "b": {"c": 2}}

    def test_dialog_manager_property(self):
        gui = MagicMock()
        dm = MagicMock()
        vm = ValidationManager(gui, dialog_manager=dm)
        assert vm.dialog_manager is dm
