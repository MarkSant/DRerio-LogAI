"""Extended unit tests for ui/components/validation_manager.py."""

from __future__ import annotations

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


class TestValidationManagerExtended8:
    def test_project_status_meta_icons(self):
        meta = project_status_meta()
        assert meta["pending"][0] == "⏳"
        assert meta["processing"][0] == "🔁"
        assert meta["failed"][0] == "⚠️"

    def test_status_symbols_all_keys(self):
        assert len(STATUS_SYMBOLS) == 4
        assert isinstance(STATUS_SYMBOLS["arena"], str)
