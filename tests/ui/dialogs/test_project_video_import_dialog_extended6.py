"""Extended unit tests for ui/dialogs/project_video_import_dialog.py (Part 6)."""

from __future__ import annotations

from zebtrack.ui.dialogs.project_video_import_dialog import SubjectEntriesDialog


class TestProjectVideoImportDialogExtended6:
    """Test SubjectEntriesDialog helper methods and input coercion."""

    def test_coerce_day_valid_positive_integer(self):
        assert SubjectEntriesDialog._coerce_day(5, fallback=1) == 5
        assert SubjectEntriesDialog._coerce_day("10", fallback=1) == 10

    def test_coerce_day_zero_or_negative(self):
        assert SubjectEntriesDialog._coerce_day(0, fallback=3) == 3
        assert SubjectEntriesDialog._coerce_day(-5, fallback=2) == 2

    def test_coerce_day_invalid_types(self):
        assert SubjectEntriesDialog._coerce_day(None, fallback=1) == 1
        assert SubjectEntriesDialog._coerce_day("invalid", fallback=4) == 4
        assert SubjectEntriesDialog._coerce_day([], fallback=2) == 2

    def test_coerce_day_large_value(self):
        assert SubjectEntriesDialog._coerce_day("365", fallback=1) == 365
