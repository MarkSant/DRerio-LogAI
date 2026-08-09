"""First-launch language chooser.

Deliberately the most dependency-free module in ``zebtrack.ui``: it runs before
settings are loaded, before the translator is installed, before the theme is set
up and before the DI container exists.  It may therefore import nothing from
``zebtrack`` beyond :mod:`zebtrack.i18n`'s constants -- no widget factory, no
dialog manager, no ttkbootstrap.

Its own text is **not** translated and never will be.  It is the one dialog that
has to be readable by someone who has not yet told us which language they read,
so every label is bilingual and hardcoded -- hence the ``i18n: file-exempt``
marker below, which keeps the extraction scanner and its guard test off this
module.
"""

# i18n: file-exempt -- bilingual by design, see the module docstring.

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import structlog

from zebtrack.i18n import DEFAULT_LANGUAGE, normalize_language

log = structlog.get_logger(__name__)

# (value, label) in display order. English first: it is the default.
LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("pt_BR", "Português (Brasil)"),
)

_TITLE = "Language / Idioma"
_PROMPT = "Choose your language:\nEscolha seu idioma:"
_CONFIRM = "Continue / Continuar"
_HINT = "You can change this later in Settings / Você pode mudar depois em Configurações"


def ask_language(root: Any, *, initial: str = DEFAULT_LANGUAGE) -> str:
    """Ask the user to pick a language, modally.

    Args:
        root: An existing, typically withdrawn, ``Tk`` root.
        initial: Option preselected when the dialog opens.

    Returns:
        One of the values in :data:`LANGUAGE_CHOICES`. Closing the window or
        pressing Escape returns *initial* unchanged: dismissing must never leave
        the application without a language, and it must not silently change one
        either. On first launch *initial* is English, so a dismissed dialog
        starts in English; reopened from Settings it keeps the language already
        in use.
    """
    # A caller may pass whatever is stored in the settings file; an unreadable
    # value must not preselect a radio button that does not exist.
    initial = normalize_language(initial) or DEFAULT_LANGUAGE

    selected = tk.StringVar(master=root, value=initial)
    result: dict[str, str] = {"value": initial}

    dialog = tk.Toplevel(root)
    dialog.title(_TITLE)
    dialog.transient(root)
    dialog.resizable(False, False)

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=_PROMPT, justify="left").pack(anchor="w", pady=(0, 12))

    for value, label in LANGUAGE_CHOICES:
        ttk.Radiobutton(frame, text=label, value=value, variable=selected).pack(anchor="w", pady=2)

    ttk.Label(frame, text=_HINT, justify="left", foreground="#666666").pack(
        anchor="w", pady=(12, 0)
    )

    def confirm() -> None:
        result["value"] = selected.get()
        dialog.destroy()

    def dismiss() -> None:
        # Escape / window close means "cancel", so keep the language that was
        # already in effect. Forcing DEFAULT_LANGUAGE here would turn a
        # cancelled Settings -> Language dialog into a silent switch to English.
        result["value"] = initial
        dialog.destroy()

    ttk.Button(frame, text=_CONFIRM, command=confirm).pack(pady=(16, 0))

    dialog.protocol("WM_DELETE_WINDOW", dismiss)
    dialog.bind("<Escape>", lambda _event: dismiss())
    dialog.bind("<Return>", lambda _event: confirm())

    _center_on_screen(dialog)
    dialog.grab_set()
    dialog.focus_force()
    root.wait_window(dialog)

    chosen = result["value"]
    log.info("i18n.language_dialog.chosen", language=chosen)
    return chosen


def _center_on_screen(window: Any) -> None:
    """Place *window* in the middle of the screen.

    Centred on the screen rather than on the parent: the parent root is
    withdrawn at this point and has no meaningful geometry yet.
    """
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
