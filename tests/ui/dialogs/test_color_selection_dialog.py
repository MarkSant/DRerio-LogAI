"""Tests for ColorSelectionDialog apply logic."""

from typing import Any, cast

from zebtrack.ui.dialogs.color_selection_dialog import ColorSelectionDialog


class _DummyVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self):
        return self._value


def _build_dialog(selected: str = "green") -> ColorSelectionDialog:
    dialog = cast(Any, ColorSelectionDialog.__new__(ColorSelectionDialog))
    dialog.selected_color = _DummyVar(selected)
    # (stable key, displayed label, BGR, hex) -- apply() matches on the key, so
    # the lookup no longer depends on the interface language.
    dialog.colors = [
        ("green", "Green", (0, 128, 0), "#008000"),
        ("blue", "Blue", (255, 0, 0), "#0000FF"),
    ]
    dialog.result = None
    return cast(ColorSelectionDialog, dialog)


def test_apply_sets_result_for_matching_color():
    dialog = _build_dialog(selected="blue")

    dialog.apply()

    assert dialog.result == {
        "key": "blue",
        "name": "Blue",
        "rgb": (255, 0, 0),
        "hex": "#0000FF",
    }


def test_apply_leaves_result_when_no_match():
    dialog = _build_dialog(selected="nonexistent")

    dialog.apply()

    assert dialog.result is None
