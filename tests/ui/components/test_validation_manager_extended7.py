"""Extended unit tests for ui/components/validation_manager.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import ValidationManager


class TestValidationManagerExtended7:
    """Test ValidationManager FPS, intervals, and threshold validation logic."""

    def test_save_global_config_invalid_fps(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()
        vm = ValidationManager(gui)

        values = {
            "video_processing": {
                "fps": 0.0,  # Invalid: must be > 0
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
                "polyorder": 2,
            },
        }

        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()
        assert "fps" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_save_global_config_invalid_processing_interval(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()
        vm = ValidationManager(gui)

        values = {
            "video_processing": {
                "fps": 30.0,
                "processing_interval": 0,  # Invalid: must be > 0
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
        assert "interval" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_save_global_config_invalid_display_interval(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()
        vm = ValidationManager(gui)

        values = {
            "video_processing": {
                "fps": 30.0,
                "processing_interval": 1,
                "display_interval": 0,  # Invalid: must be > 0
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
        assert "display interval" in gui.dialog_manager.show_error.call_args[0][1].lower()

    def test_save_global_config_invalid_offset(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()
        vm = ValidationManager(gui)

        values = {
            "video_processing": {
                "fps": 30.0,
                "processing_interval": 1,
                "display_interval": 1,
                "processing_offset": -1,  # Invalid: must be >= 0
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
        assert "offset" in gui.dialog_manager.show_error.call_args[0][1].lower()
