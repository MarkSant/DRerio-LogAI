"""Tests for ``BusyDialog`` (the "Finalizing recording..." window, audit A6-07)."""

from __future__ import annotations

import pytest

from zebtrack.ui.dialogs.busy_dialog import BusyDialog

pytestmark = pytest.mark.gui


def test_shows_the_message_and_ignores_the_close_button(tkinter_root):
    dialog = BusyDialog(tkinter_root, "Finalizing recording...")
    try:
        assert dialog.window is not None
        assert dialog.window.title() == "Finalizing recording..."
        assert dialog.label.cget("text") == "Finalizing recording..."
        # WM_DELETE_WINDOW is a no-op: closing it would not stop the teardown.
        handler = dialog.window.protocol("WM_DELETE_WINDOW")
        assert handler
        dialog.window.tk.call(handler)
        assert dialog.window.winfo_exists()
    finally:
        dialog.close()


def test_close_destroys_the_window_and_is_idempotent(tkinter_root):
    dialog = BusyDialog(tkinter_root, "Please wait")
    window = dialog.window
    assert window is not None

    dialog.close()
    dialog.close()

    assert dialog.window is None
    assert not window.winfo_exists()
