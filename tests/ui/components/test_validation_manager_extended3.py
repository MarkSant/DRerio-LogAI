"""Extended unit tests for ui/components/validation_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import (
    STATUS_SYMBOLS,
    ValidationManager,
    project_status_meta,
)


class TestValidationManagerExtended3:
    """Test ValidationManager deep merge, status metadata, and DI properties."""

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
