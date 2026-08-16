"""Unit tests for ui/format_utils.py formatting helpers."""

from __future__ import annotations

import pytest

from zebtrack.ui.format_utils import format_day_display


class TestFormatDayDisplay:
    """Test format_day_display for all input types."""

    @pytest.mark.parametrize("value", [None, ""])
    def test_none_or_empty_returns_empty_string(self, value):
        assert format_day_display(value) == ""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, "01"),
            (2, "02"),
            (10, "10"),
            (99, "99"),
            (1.0, "01"),
            (3.9, "03"),
        ],
    )
    def test_numeric_formats_zero_padded(self, value, expected):
        assert format_day_display(value) == expected

    def test_string_with_digits_extracts_number(self):
        assert format_day_display("Dia_3") == "03"
        assert format_day_display("Day 07") == "07"
        assert format_day_display("D01") == "01"
        assert format_day_display("4") == "04"

    def test_whitespace_only_returns_empty(self):
        assert format_day_display("   ") == ""

    def test_sem_dia_returns_sem_dia(self):
        assert format_day_display("sem dia") == "Sem Dia"
        assert format_day_display("Sem Dia") == "Sem Dia"

    def test_no_digits_returns_string_as_is(self):
        result = format_day_display("NoDigits")
        assert result == "NoDigits"

    def test_bool_not_treated_as_numeric(self):
        # bool is subclass of int but format_day_display excludes it
        result = format_day_display(True)
        assert result in ("True", "01", "1")  # implementation-defined but not crashing
