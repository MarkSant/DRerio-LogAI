"""Tests for UI format utilities."""

from zebtrack.ui.format_utils import format_day_display


def test_format_day_display_none_or_empty():
    assert format_day_display(None) == ""
    assert format_day_display("") == ""
    assert format_day_display("   ") == ""


def test_format_day_display_numeric():
    assert format_day_display(1) == "01"
    assert format_day_display(12.0) == "12"
    assert format_day_display(True) == "True"


def test_format_day_display_sem_dia():
    assert format_day_display("Sem Dia") == "Sem Dia"
    assert format_day_display("sem dia") == "Sem Dia"


def test_format_day_display_extracts_digits():
    assert format_day_display("Dia 3") == "03"
    assert format_day_display("D10") == "10"


def test_format_day_display_fallback():
    assert format_day_display("ABC") == "ABC"
