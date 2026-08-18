"""Extended unit tests for ui/components/validation_manager.py (Part 8)."""

from __future__ import annotations

from zebtrack.ui.components.validation_manager import STATUS_SYMBOLS, project_status_meta


class TestValidationManagerExtended8:
    """Test ValidationManager shared status symbols and project status metadata."""

    def test_status_symbols_dictionary(self):
        assert "arena" in STATUS_SYMBOLS
        assert "rois" in STATUS_SYMBOLS
        assert "trajectory" in STATUS_SYMBOLS
        assert "summary" in STATUS_SYMBOLS

    def test_project_status_meta_contents(self):
        meta = project_status_meta()
        assert "pending" in meta
        assert "processing" in meta
        assert "processed" in meta
        assert "complete" in meta
        assert "failed" in meta

        # Check tuple format: (icon, label)
        icon, label = meta["complete"]
        assert icon == "✅"
        assert len(label) > 0

    def test_project_status_meta_icons(self):
        meta = project_status_meta()
        assert meta["pending"][0] == "⏳"
        assert meta["processing"][0] == "🔁"
        assert meta["failed"][0] == "⚠️"

    def test_status_symbols_all_keys(self):
        assert len(STATUS_SYMBOLS) == 4
        assert isinstance(STATUS_SYMBOLS["arena"], str)
