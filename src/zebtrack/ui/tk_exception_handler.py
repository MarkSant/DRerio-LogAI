"""Last-resort handler for exceptions raised inside Tkinter callbacks.

Tk's default ``report_callback_exception`` prints a traceback to stderr. The
packaged application has no console attached, so an exception escaping a widget
callback is indistinguishable from the button doing nothing at all: no dialog,
no log entry, no clue. That is exactly how a detector-parameter validation
error went unreported for as long as it did.

This installs a handler that records the traceback through structlog and tells
the user that something failed.

It is a NET, not a boundary. Every entry it logs means some call site is
missing its own ``except`` — the handler cannot know what the user was doing,
so it cannot offer anything better than "this failed, see the log". Treat
``ui.callback.unhandled`` in the log as a bug report against the call site.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import structlog

from zebtrack.i18n import _

log = structlog.get_logger()


def handle_tk_callback_exception(
    exc_type: type[BaseException],
    exc_value: BaseException | None,
    exc_traceback: TracebackType | None,
    *,
    messagebox_module: Any | None = None,
    parent: Any | None = None,
) -> None:
    """Log an exception that escaped a Tk callback and tell the user.

    Args:
        exc_type: Exception class, as passed by Tk.
        exc_value: Exception instance, as passed by Tk.
        exc_traceback: Traceback, as passed by Tk.
        messagebox_module: Injected for tests; defaults to ``tkinter.messagebox``.
        parent: Optional parent window for the dialog.
    """
    log.critical(
        "ui.callback.unhandled",
        error_type=exc_type.__name__,
        error=str(exc_value),
        exc_info=(exc_type, exc_value, exc_traceback),
    )

    dialogs: Any = messagebox_module
    if dialogs is None:
        from tkinter import messagebox

        dialogs = messagebox

    # The dialog is best effort: this runs while the app is already failing, and
    # a second exception raised here would land back in Tk's default handler and
    # lose the first one. Whatever happens, the log entry above survives.
    try:
        message = _(
            "An unexpected error occurred and was recorded in the log.\n\n{error_type}: {error}"
        ).format(error_type=exc_type.__name__, error=exc_value)
        if parent is not None:
            dialogs.showerror(_("Unexpected Error"), message, parent=parent)
        else:
            dialogs.showerror(_("Unexpected Error"), message)
    # except Exception justified: the net must never raise from inside itself.
    except Exception:
        log.debug("ui.callback.unhandled.dialog_failed", exc_info=True)


def install_tk_exception_handler(root: Any, *, messagebox_module: Any | None = None) -> None:
    """Route Tk callback exceptions on *root* through :func:`handle_tk_callback_exception`.

    Args:
        root: The ``tkinter.Tk`` instance whose callbacks should be covered.
        messagebox_module: Injected for tests; defaults to ``tkinter.messagebox``.
    """

    def _report(
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        handle_tk_callback_exception(
            exc_type,
            exc_value,
            exc_traceback,
            messagebox_module=messagebox_module,
            parent=root,
        )

    root.report_callback_exception = _report
    log.debug("ui.callback.handler_installed")
