"""Tests for TemplateDialog apply logic."""

from typing import Any, cast

from zebtrack.ui.dialogs.template_dialog import TemplateDialog


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def _build_dialog(template_type="grid", lanes="3", rows="2", cols="4"):
    dialog = cast(Any, TemplateDialog.__new__(TemplateDialog))
    dialog.template_type = _DummyVar(template_type)
    dialog.num_lanes = _DummyVar(lanes)
    dialog.num_rows = _DummyVar(rows)
    dialog.num_cols = _DummyVar(cols)
    dialog.result = None
    return cast(TemplateDialog, dialog)


def test_apply_sets_result_for_valid_values():
    dialog = _build_dialog(template_type="horizontal", lanes="5", rows="3", cols="4")

    dialog.apply()

    assert dialog.result == {
        "type": "horizontal",
        "lanes": 5,
        "rows": 3,
        "cols": 4,
    }


def test_apply_sets_none_on_invalid_values():
    dialog = _build_dialog(lanes="invalid")

    dialog.apply()

    assert dialog.result is None
