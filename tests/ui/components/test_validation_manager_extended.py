"""Extended unit tests for ValidationManager in ui/components/validation_manager.py."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.components.validation_manager import (
    STATUS_SYMBOLS,
    ValidationManager,
    project_status_meta,
)


class TestValidationManagerExtended:
    """Test status metadata, deep merge dictionaries, and status formatting helpers."""

    def test_status_symbols_constant(self):
        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

    def test_project_status_meta(self):
        meta = project_status_meta()
        assert "pending" in meta
        assert "processing" in meta
        assert "complete" in meta
        assert "failed" in meta
        assert meta["complete"][0] == "✅"

    def test_deep_merge_dicts(self):
        base: dict[str, Any] = {
            "a": 1,
            "b": {"x": 10, "y": 20},
            "c": [1, 2],
        }
        override: dict[str, Any] = {
            "b": {"y": 25, "z": 30},
            "d": 99,
        }
        merged = ValidationManager._deep_merge_dicts(base, override)
        assert merged["a"] == 1
        assert merged["b"]["x"] == 10
        assert merged["b"]["y"] == 25
        assert merged["b"]["z"] == 30
        assert merged["d"] == 99
        # Base is not mutated
        sub_b: dict[str, int] = base["b"]
        assert sub_b["y"] == 20

    def test_format_status_token(self):
        arena_sym = STATUS_SYMBOLS["arena"]
        assert ValidationManager.format_status_token(True, "arena") == f"{arena_sym} ✓"
        assert ValidationManager.format_status_token(False, "arena") == f"{arena_sym} ✗"

    def test_format_subject_label(self):
        assert ValidationManager.format_subject_label(1) == "01"
        assert ValidationManager.format_subject_label(42) == "42"
        assert ValidationManager.format_subject_label("Sujeito_1") == "Sujeito_1"
        assert ValidationManager.format_subject_label(None) == "??"
        assert ValidationManager.format_subject_label("") == "??"
