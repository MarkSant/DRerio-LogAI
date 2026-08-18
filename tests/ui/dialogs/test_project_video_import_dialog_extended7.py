"""Extended unit tests for ui/dialogs/project_video_import_dialog.py (Part 7)."""

from __future__ import annotations

from zebtrack.ui.dialogs.project_video_import_dialog import SubjectEntriesDialog


class TestProjectVideoImportDialogExtended7:
    """Test SubjectEntriesDialog validation and day coercion edge cases."""

    def test_coerce_day_float_string(self):
        # int("12.5") raises ValueError, should return fallback
        assert SubjectEntriesDialog._coerce_day("12.5", fallback=5) == 5

    def test_coerce_day_whitespace_string(self):
        assert SubjectEntriesDialog._coerce_day("  ", fallback=1) == 1

    def test_coerce_day_string_with_leading_zeros(self):
        assert SubjectEntriesDialog._coerce_day("007", fallback=1) == 7
