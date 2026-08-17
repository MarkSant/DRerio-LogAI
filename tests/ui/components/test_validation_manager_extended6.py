"""Extended unit tests for ui/components/validation_manager.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import ValidationManager


class TestValidationManagerExtended6:
    """Test ValidationManager trajectory smoothing polynomial order and window length checks."""

    def test_save_global_config_invalid_polyorder(self):
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
                "flush_row_threshold": 100,
            },
            "trajectory_smoothing": {
                "window_length": 5,
                "polyorder": 0,  # Invalid: polyorder must be at least 1
            },
        }

        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()
        assert "polyorder" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_save_global_config_even_window_length(self):
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
                "flush_row_threshold": 100,
            },
            "trajectory_smoothing": {
                "window_length": 4,  # Invalid: must be odd
                "polyorder": 2,
            },
        }

        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()
        assert "window length" in gui.dialog_manager.show_error.call_args[0][1].lower()
