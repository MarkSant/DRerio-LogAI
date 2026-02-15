"""GUI-marked coverage tests for UI format utilities."""

import pytest

from zebtrack.ui.format_utils import format_day_display


@pytest.mark.gui
def test_format_day_display_gui_numeric_and_text() -> None:
    assert format_day_display(7) == "07"
    assert format_day_display("Dia 14") == "14"


@pytest.mark.gui
def test_format_day_display_gui_empty_and_sem_dia() -> None:
    assert format_day_display(None) == ""
    assert format_day_display("sem dia") == "Sem Dia"
