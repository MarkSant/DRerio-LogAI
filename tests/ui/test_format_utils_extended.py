"""Extended unit tests for ui/format_utils.py."""

from __future__ import annotations

from zebtrack.ui.format_utils import format_day_display


class TestFormatUtilsExtended:
    """Test format_day_display string and number formatting."""

    def test_format_day_display_none_and_empty(self):
        assert format_day_display(None) == ""
        assert format_day_display("") == ""
        assert format_day_display("   ") == ""

    def test_format_day_display_integers_and_floats(self):
        assert format_day_display(1) == "01"
        assert format_day_display(12) == "12"
        assert format_day_display(5.0) == "05"
        assert format_day_display(True) == "True"  # Boolean should not be treated as int

    def test_format_day_display_sem_dia(self):
        assert format_day_display("Sem Dia") == "Sem Dia"
        assert format_day_display("sem dia") == "Sem Dia"
        assert format_day_display("SEM DIA") == "Sem Dia"

    def test_format_day_display_embedded_numbers(self):
        assert format_day_display("Day 3") == "03"
        assert format_day_display("D04") == "04"
        assert format_day_display("no_digits_here") == "no_digits_here"
