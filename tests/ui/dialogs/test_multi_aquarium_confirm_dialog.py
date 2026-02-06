"""Tests for MultiAquariumConfirmDialog callbacks."""

from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.ui.dialogs import multi_aquarium_confirm_dialog as dialog_module


class _DummyIntVar:
    def __init__(self, value: int) -> None:
        self._value = value

    def get(self) -> int:
        return self._value


def _build_dialog(value: int) -> dialog_module.MultiAquariumConfirmDialog:
    dialog = cast(
        Any,
        dialog_module.MultiAquariumConfirmDialog.__new__(dialog_module.MultiAquariumConfirmDialog),
    )
    dialog._aquarium_count = _DummyIntVar(value)
    dialog._on_single = MagicMock()
    dialog._on_multi = MagicMock()
    dialog._on_cancel = MagicMock()
    dialog.result = None
    dialog.ok = MagicMock()
    return cast(dialog_module.MultiAquariumConfirmDialog, dialog)


def test_on_confirm_calls_single_callback():
    dialog = _build_dialog(1)

    dialog._on_confirm()

    assert dialog.result == 1
    cast(MagicMock, dialog._on_single).assert_called_once()
    cast(MagicMock, dialog._on_multi).assert_not_called()
    cast(MagicMock, dialog.ok).assert_called_once()


def test_on_confirm_calls_multi_callback():
    dialog = _build_dialog(2)

    dialog._on_confirm()

    assert dialog.result == 2
    cast(MagicMock, dialog._on_multi).assert_called_once()
    cast(MagicMock, dialog._on_single).assert_not_called()
    cast(MagicMock, dialog.ok).assert_called_once()


def test_cancel_clears_result_and_invokes_cancel(monkeypatch):
    dialog = _build_dialog(1)
    dialog.result = 1
    cancel_stub = MagicMock()
    monkeypatch.setattr(dialog_module.simpledialog.Dialog, "cancel", cancel_stub)

    dialog.cancel()

    assert dialog.result is None
    cast(MagicMock, dialog._on_cancel).assert_called_once()
    cancel_stub.assert_called_once()


def test_get_result_returns_current_value():
    dialog = _build_dialog(2)
    dialog.result = 2

    assert dialog.get_result() == 2
