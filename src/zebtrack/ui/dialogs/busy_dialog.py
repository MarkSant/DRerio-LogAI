"""Small modal "please wait" window for work that runs off the Tk thread.

Used while a live session is being finalised (audit A6-07): the teardown runs
on a worker, the window stays responsive, and the grab keeps the operator from
starting another session or closing the project half-way through the flush.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import structlog

log = structlog.get_logger()


class BusyDialog:
    """Modal, non-closable message window; ``close()`` is idempotent."""

    def __init__(self, parent: Any, message: str) -> None:
        window = tk.Toplevel(parent)
        self.window: tk.Toplevel | None = window
        window.title(message)
        window.resizable(False, False)
        window.transient(parent)
        # Closing it would not stop the work it announces.
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.label = ttk.Label(window, text=message, padding=(24, 16))
        self.label.pack()
        window.update_idletasks()
        try:
            window.grab_set()
        except tk.TclError as exc:
            # Another grab is active (or the window is not viewable yet):
            # the message is still shown, only not modal.
            log.debug("busy_dialog.grab_failed", error=str(exc))

    def close(self) -> None:
        """Release the grab and destroy the window (safe to call twice)."""
        window, self.window = self.window, None
        if window is None:
            return
        try:
            window.grab_release()
            window.destroy()
        except tk.TclError as exc:
            log.debug("busy_dialog.close_failed", error=str(exc))
