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
    _make_transient_if_the_master_is_visible(dialog, root)
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


def _make_transient_if_the_master_is_visible(dialog: Any, root: Any) -> None:
    """Apply ``transient`` only when it will not make *dialog* disappear.

    **A transient window inherits its master's mapped state.** If the master is
    withdrawn, so is the transient -- and neither ``deiconify()`` nor ``lift()``
    overrides that; measured on Windows, the dialog stays ``state='withdrawn'``,
    unviewable, sized 1x1.

    That is fatal here, because ``run_app`` calls ``root.withdraw()`` before
    asking for a language: on a genuine first launch the chooser was created,
    never shown, and ``wait_window`` below then blocked forever on a window
    nobody could see, focus or close. The application hung with no window and
    no error -- launched from the desktop shortcut, double-clicking the icon
    appeared to do nothing at all.

    Reopened from **Settings -> Language** the root is mapped, and there the
    transient relationship is worth keeping: correct stacking above the main
    window, and no second taskbar button. So it is applied whenever it is safe.

    ``winfo_viewable`` is asked of the root rather than assumed from the call
    site, because both callers reach the same function.
    """
    try:
        master_is_visible = bool(root.winfo_viewable())
    except tk.TclError:
        # A root that cannot answer is not one to tie this dialog's visibility
        # to. Showing a chooser without transient behaviour is a cosmetic loss;
        # not showing it at all stops the application.
        log.debug("i18n.language_dialog.viewable_check_failed", exc_info=True)
        return

    if master_is_visible:
        dialog.transient(root)


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
