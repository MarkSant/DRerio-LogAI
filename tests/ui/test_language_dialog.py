"""Tests for the first-launch language chooser.

This dialog runs before settings are loaded and before the translator is
installed, so it has two properties worth pinning: it never returns something
the settings model would reject, and dismissing it still yields a usable
language rather than blocking startup.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from zebtrack.i18n import SUPPORTED_LANGUAGES
from zebtrack.ui import language_dialog
from zebtrack.ui.language_dialog import LANGUAGE_CHOICES, ask_language

pytestmark = pytest.mark.gui


def _drive(root, driver, timeout_ms: int = 5000):
    """Run *driver* against the dialog once it appears, with a hard stop.

    The dialog is modal (``wait_window``), so the only way to act on it is from
    inside the event loop it is running. The watchdog matters: without it a
    driver that fails to find its widget would hang the whole suite instead of
    failing one test.
    """
    state: dict[str, object] = {"acted": False}

    def find_dialog():
        return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]

    def attempt():
        if state["acted"]:
            return
        dialogs = find_dialog()
        if not dialogs:
            root.after(20, attempt)
            return
        state["acted"] = True
        state["texts"] = _all_texts(dialogs[0])
        driver(dialogs[0])

    def watchdog():
        if not state["acted"]:
            state["timed_out"] = True
            for dialog in find_dialog():
                dialog.destroy()

    root.after(20, attempt)
    root.after(timeout_ms, watchdog)
    result = ask_language(root)
    assert not state.get("timed_out"), "language dialog never appeared"
    return result, state.get("texts", [])


def _all_texts(widget, found=None):
    found = found if found is not None else []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except tk.TclError:
            text = ""
        if text:
            found.append(str(text))
        _all_texts(child, found)
    return found


def _widgets_of_class(widget, cls, found=None):
    found = found if found is not None else []
    for child in widget.winfo_children():
        if child.winfo_class() == cls:
            found.append(child)
        _widgets_of_class(child, cls, found)
    return found


def _confirm(dialog):
    _widgets_of_class(dialog, "TButton")[0].invoke()


def test_choices_are_all_supported_languages():
    """A choice the settings model would reject must not be offerable."""
    offered = {value for value, _label in LANGUAGE_CHOICES}
    assert offered == set(SUPPORTED_LANGUAGES)


def test_english_is_offered_first():
    """English is the default, so it leads."""
    assert LANGUAGE_CHOICES[0][0] == "en"


def test_dialog_is_bilingual_so_it_reads_before_a_language_is_chosen():
    assert "Language / Idioma" in language_dialog._TITLE
    labels = [label for _value, label in LANGUAGE_CHOICES]
    assert "English" in labels
    assert any("Portugu" in label for label in labels)


def test_confirming_the_default_returns_english(tkinter_root):
    result, texts = _drive(tkinter_root, _confirm)
    assert result == "en"
    assert any("English" in text for text in texts)
    assert any("Portugu" in text for text in texts)


def test_selecting_portuguese_returns_pt_br(tkinter_root):
    def choose_portuguese(dialog):
        for radio in _widgets_of_class(dialog, "TRadiobutton"):
            if "Portugu" in str(radio.cget("text")):
                radio.invoke()
        _confirm(dialog)

    result, _texts = _drive(tkinter_root, choose_portuguese)
    assert result == "pt_BR"


def test_dismissing_on_first_launch_yields_english(tkinter_root):
    """Dismissing must not leave the application without a language."""
    result, _texts = _drive(tkinter_root, lambda dialog: dialog.destroy())
    assert result == "en"


def test_dismissing_keeps_the_current_language(tkinter_root):
    """Cancel means "keep what I had", not "switch me to English".

    Reached from Settings -> Language while running in Portuguese: closing the
    dialog without confirming must not silently change the language.
    """
    state: dict[str, object] = {}

    def attempt():
        dialogs = [w for w in tkinter_root.winfo_children() if isinstance(w, tk.Toplevel)]
        if not dialogs:
            tkinter_root.after(20, attempt)
            return
        state["done"] = True
        dialogs[0].destroy()

    tkinter_root.after(20, attempt)
    result = ask_language(tkinter_root, initial="pt_BR")
    assert state.get("done"), "language dialog never appeared"
    assert result == "pt_BR"


def test_unreadable_initial_value_falls_back_to_english(tkinter_root):
    """A corrupted ui.language must not preselect a nonexistent option."""
    state: dict[str, object] = {}

    def attempt():
        dialogs = [w for w in tkinter_root.winfo_children() if isinstance(w, tk.Toplevel)]
        if not dialogs:
            tkinter_root.after(20, attempt)
            return
        state["done"] = True
        dialogs[0].destroy()

    tkinter_root.after(20, attempt)
    result = ask_language(tkinter_root, initial="klingon")
    assert state.get("done"), "language dialog never appeared"
    assert result == "en"


def test_initial_selection_is_honoured(tkinter_root):
    """Reopening from Settings preselects the language already in use."""

    def confirm_without_changing(dialog):
        _confirm(dialog)

    state: dict[str, object] = {}

    def attempt():
        dialogs = [w for w in tkinter_root.winfo_children() if isinstance(w, tk.Toplevel)]
        if not dialogs:
            tkinter_root.after(20, attempt)
            return
        state["done"] = True
        confirm_without_changing(dialogs[0])

    tkinter_root.after(20, attempt)
    result = ask_language(tkinter_root, initial="pt_BR")
    assert state.get("done"), "language dialog never appeared"
    assert result == "pt_BR"


class TestTheDialogIsActuallyVisibleOnFirstLaunch:
    """The condition the other tests here never reproduce: a withdrawn root.

    ``run_app`` calls ``root.withdraw()`` and only asks for a language
    afterwards, because the answer has to be written before ``load_settings()``
    reads it. Every other test in this file receives an ordinary visible
    Toplevel from the ``tkinter_root`` fixture, which is why a dialog that is
    never mapped passed all of them.

    A transient window inherits its master's mapped state, so
    ``transient(withdrawn_root)`` produced a chooser that was created and never
    shown -- and ``wait_window`` then blocked forever. The app hung with no
    window and no error.
    """

    def test_dialog_is_viewable_when_the_root_is_withdrawn(self, tkinter_session_root):
        root = tk.Toplevel(tkinter_session_root)
        root.withdraw()
        seen: dict[str, object] = {}

        def inspect_then_close(dialog):
            dialog.update_idletasks()
            dialog.update()
            seen["viewable"] = bool(dialog.winfo_viewable())
            seen["state"] = dialog.state()
            seen["size"] = (dialog.winfo_width(), dialog.winfo_height())
            dialog.destroy()

        try:
            _drive(root, inspect_then_close)
        finally:
            root.destroy()

        assert seen["viewable"], (
            f"the chooser was never mapped: state={seen['state']!r} size={seen['size']!r}; "
            "wait_window would block on it forever"
        )
        assert seen["state"] == "normal"

    def test_transient_is_still_applied_when_the_root_is_visible(self, tkinter_root):
        """Settings -> Language reopens this over a mapped window.

        There the transient relationship earns its keep -- stacking above the
        main window, no second taskbar entry -- so the guard must not drop it
        for everyone.
        """
        tkinter_root.deiconify()
        tkinter_root.update_idletasks()
        seen: dict[str, object] = {}

        def inspect_then_close(dialog):
            dialog.update_idletasks()
            seen["master"] = dialog.wm_transient()
            seen["viewable"] = bool(dialog.winfo_viewable())
            dialog.destroy()

        _drive(tkinter_root, inspect_then_close)

        assert seen["master"], "transient was dropped over a visible root"
        assert seen["viewable"]

    def test_a_root_that_cannot_answer_still_yields_a_dialog(self, tkinter_session_root):
        """A TclError from the master must not cost us the chooser.

        Losing transient behaviour is cosmetic; losing the dialog stops startup.
        """
        root = tk.Toplevel(tkinter_session_root)
        seen: dict[str, object] = {}

        def boom():
            raise tk.TclError("bad window path name")

        root.winfo_viewable = boom  # type: ignore[method-assign]

        def inspect_then_close(dialog):
            dialog.update_idletasks()
            dialog.update()
            seen["viewable"] = bool(dialog.winfo_viewable())
            dialog.destroy()

        try:
            _drive(root, inspect_then_close)
        finally:
            del root.winfo_viewable
            root.destroy()

        assert seen["viewable"]
