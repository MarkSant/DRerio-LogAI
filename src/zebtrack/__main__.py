"""DRerio LogAI application entrypoint."""

import sys
import tkinter as tk
import traceback
from tkinter import messagebox

from zebtrack.core.app_runner import run_app
from zebtrack.logging_config import configure_logging


def _report_crash_without_a_console(exc: BaseException) -> None:
    """Show a traceback that would otherwise vanish into a closed stream.

    ``run_app`` already turns failures into a dialog, but only from the point
    the Tk root exists onwards. Everything before that -- argument parsing,
    logging setup, ``Tk()`` itself -- and any failure of the error handler
    reaches here instead, where Python's default behaviour is to print to
    ``sys.stderr`` and exit.

    **Under the desktop shortcut there is no stderr to print to.** The app is
    launched with ``pythonw.exe`` so no console window sits behind the GUI,
    which means ``sys.stderr`` is None and the interpreter's own traceback goes
    nowhere: double-clicking the icon appears to do nothing at all. That is the
    single worst outcome for someone with no terminal to fall back on, so this
    puts the traceback in a message box instead.

    Deliberately a no-op when a console exists: the traceback Python prints
    there is better than a modal dialog, and the test suite asserts on it.
    """
    if sys.stderr is not None:
        return

    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        from zebtrack.logging_config import resolve_log_path

        log_path = resolve_log_path("analysis.log")
    except Exception:
        log_path = "logs/analysis.log"

    # Untranslated on purpose, exactly like the fatal configuration dialogs in
    # core/app_runner.py: this can fire before i18n.install() has run, so there
    # is no catalogue to honour yet.
    body = (
        "DRerio LogAI could not start.\n\n"
        f"{detail}\n"
        f"The full log is at:\n{log_path}\n\n"
        "Running it from a terminal shows the same error:\n"
        "    poetry run zebtrack"
    )
    try:
        messagebox.showerror("DRerio LogAI - startup failed", body)
    except Exception:
        # No usable Tk either. The log file is the last channel, and it is
        # written by a handler that does not need a console.
        import structlog

        structlog.get_logger().critical("main.startup_failed", error=detail)


def main() -> None:
    try:
        run_app(
            tk_module=tk,
            messagebox_module=messagebox,
            configure_logging_fn=configure_logging,
        )
    except SystemExit:
        # A deliberate exit, already reported by whoever raised it.
        raise
    except BaseException as exc:
        _report_crash_without_a_console(exc)
        raise


if __name__ == "__main__":
    main()
