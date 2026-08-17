"""Extended unit tests for ui/components/validation_manager.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import ValidationManager


class TestValidationManagerExtended4:
    """Test ValidationManager configuration validation and recursive dictionary merging."""

    def test_save_global_config_invalid_fps(self):
        gui = MagicMock()
        vm = ValidationManager(gui)

        values = {
            "video_processing": {
                "fps": 0,  # Invalid FPS
                "processing_interval": 1,
                "display_interval": 1,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 1.0,
                "flush_row_threshold": 100,
            },
            "trajectory_smoothing": {
                "window_length": 5,
                "polyorder": 2,
            },
        }

        # Should trigger dialog_manager.show_error
        vm.save_global_config_from_widget(values)
        gui.dialog_manager.show_error.assert_called_once()

    def test_deep_merge_dicts_nested(self):
        base = {
            "a": 1,
            "nested": {"x": 10, "y": 20},
            "unchanged": "keep",
        }
        override = {
            "a": 2,
            "nested": {"y": 99, "z": 100},
            "new_key": "val",
        }

        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged["a"] == 2
        assert merged["unchanged"] == "keep"
        assert merged["nested"]["x"] == 10
        assert merged["nested"]["y"] == 99
        assert merged["nested"]["z"] == 100
        assert merged["new_key"] == "val"
