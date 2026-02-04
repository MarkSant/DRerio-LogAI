"""Tests for MissingMetadataDialog validation and apply logic."""

from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.ui.dialogs import missing_metadata_dialog as dialog_module


class _DummyVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self):
        return self._value


def _build_dialog(
    day: str = "1",
    group: str = "A",
    cobaia: str = "2",
) -> dialog_module.MissingMetadataDialog:
    dialog = cast(
        Any,
        dialog_module.MissingMetadataDialog.__new__(dialog_module.MissingMetadataDialog),
    )
    dialog.day_var = _DummyVar(day)
    dialog.group_var = _DummyVar(group)
    dialog.cobaia_var = _DummyVar(cobaia)
    dialog.result = None
    return cast(dialog_module.MissingMetadataDialog, dialog)


def test_validate_accepts_valid_values(monkeypatch):
    dialog = _build_dialog(day="3", group="Group", cobaia="4")
    monkeypatch.setattr(dialog_module.messagebox, "showerror", MagicMock())

    assert dialog.validate() == 1


def test_validate_rejects_non_integer_fields(monkeypatch):
    dialog = _build_dialog(day="x", group="Group", cobaia="2")
    showerror = MagicMock()
    monkeypatch.setattr(dialog_module.messagebox, "showerror", showerror)

    assert dialog.validate() == 0
    showerror.assert_called_once()


def test_validate_rejects_empty_group(monkeypatch):
    dialog = _build_dialog(day="1", group="   ", cobaia="2")
    showerror = MagicMock()
    monkeypatch.setattr(dialog_module.messagebox, "showerror", showerror)

    assert dialog.validate() == 0
    showerror.assert_called_once()


def test_apply_sets_result():
    dialog = _build_dialog(day="2", group="Group", cobaia="5")

    dialog.apply()

    assert dialog.result == {"day": 2, "group": "Group", "cobaia": 5}
