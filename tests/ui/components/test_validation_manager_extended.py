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


class TestValidationManagerExtended2:
    def test_project_status_meta(self):
        meta = project_status_meta()
        assert "pending" in meta
        assert "processing" in meta
        assert "processed" in meta
        assert "complete" in meta
        assert "failed" in meta

        icon, label = meta["complete"]
        assert icon == "✅"
        assert len(label) > 0

    def test_deep_merge_dicts(self):
        base = {"a": 1, "b": {"c": 2, "d": 3}, "e": [1, 2]}
        override = {"b": {"d": 4, "f": 5}, "e": [3, 4], "g": 6}

        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged["a"] == 1
        assert merged["b"]["c"] == 2
        assert merged["b"]["d"] == 4
        assert merged["b"]["f"] == 5
        assert merged["e"] == [3, 4]
        assert merged["g"] == 6

    def test_dialog_manager_property_injected_and_fallback(self):
        gui = MagicMock()
        injected_dm = MagicMock()
        vm = ValidationManager(gui, dialog_manager=injected_dm)
        assert vm.dialog_manager is injected_dm

        gui.dialog_manager = MagicMock()
        vm_fallback = ValidationManager(gui, dialog_manager=None)
        assert vm_fallback.dialog_manager is gui.dialog_manager

    def test_compose_overview_status_line_empty(self):
        vm = ValidationManager(MagicMock())
        res = vm.compose_overview_status_line(0, Counter())
        assert "No video registered" in res or "Nenhum vídeo" in res

    def test_compose_overview_status_line_populated(self):
        vm = ValidationManager(MagicMock())
        counts = Counter({"pending": 2, "complete": 5, "failed": 1, "unknown_status": 3})
        res = vm.compose_overview_status_line(11, counts)
        assert "11" in res
        assert "✅ 5" in res
        assert "⏳ 2" in res
        assert "⚠️ 1" in res
        assert "+ 3" in res


class TestValidationManagerExtended3:
    def test_status_symbols_and_meta(self):
        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

        meta = project_status_meta()
        assert "pending" in meta
        assert "complete" in meta
        assert "failed" in meta

    def test_dialog_manager_property_injected_and_fallback(self):
        gui = MagicMock()
        gui.dialog_manager = MagicMock()

        mock_dm = MagicMock()
        vm_injected = ValidationManager(gui, dialog_manager=mock_dm)
        assert vm_injected.dialog_manager is mock_dm

        vm_fallback = ValidationManager(gui, dialog_manager=None)
        assert vm_fallback.dialog_manager is gui.dialog_manager

    def test_deep_merge_dicts(self):
        base = {"a": 1, "nested": {"x": 10, "y": 20}}
        override = {"b": 2, "nested": {"y": 30, "z": 40}}

        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged["a"] == 1
        assert merged["b"] == 2
        assert merged["nested"]["x"] == 10
        assert merged["nested"]["y"] == 30
        assert merged["nested"]["z"] == 40

    def test_deep_merge_dicts_empty(self):
        assert ValidationManager._deep_merge_dicts({}, {}) == {}
        assert ValidationManager._deep_merge_dicts({"k": "v"}, {}) == {"k": "v"}
        assert ValidationManager._deep_merge_dicts({}, {"k": "v"}) == {"k": "v"}


class TestValidationManagerExtended4:
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


class TestValidationManagerExtended5:
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


class TestValidationManagerExtended6:
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


class TestValidationManagerExtended7:
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


class TestValidationManagerExtended8:
    def test_project_status_meta_icons(self):
        meta = project_status_meta()
        assert meta["pending"][0] == "⏳"
        assert meta["processing"][0] == "🔁"
        assert meta["failed"][0] == "⚠️"

    def test_status_symbols_all_keys(self):
        assert len(STATUS_SYMBOLS) == 4
        assert isinstance(STATUS_SYMBOLS["arena"], str)
