"""Extended unit tests for ui/components/validation_manager.py."""

from __future__ import annotations

from collections import Counter
from unittest.mock import MagicMock

from zebtrack.ui.components.validation_manager import (
    ValidationManager,
    project_status_meta,
)


class TestValidationManagerExtended2:
    """Test ValidationManager constants, metadata helpers, status line, and deep merge utility."""

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
