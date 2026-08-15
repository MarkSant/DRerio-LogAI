"""The net under every Tk callback.

Tk's default ``report_callback_exception`` writes a traceback to stderr. The
packaged app has no console, so anything reaching it is lost entirely. These
tests cover the replacement: it logs, it shows a dialog, and it never raises
from inside itself (a second exception here would land back in Tk's default
handler and destroy the first one's traceback).

This is a net, not a boundary — see ``tests/ui/test_detector_parameter_ui_boundary.py``
for the call sites that are supposed to make it unnecessary.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.tk_exception_handler import (
    handle_tk_callback_exception,
    install_tk_exception_handler,
)


def _raise_and_capture(exc: BaseException):
    try:
        raise exc
    except BaseException as caught:
        return type(caught), caught, caught.__traceback__


def test_handler_shows_a_dialog() -> None:
    messagebox = MagicMock()

    handle_tk_callback_exception(
        *_raise_and_capture(ValueError("boom")), messagebox_module=messagebox
    )

    messagebox.showerror.assert_called_once()
    title, message = messagebox.showerror.call_args.args
    assert title
    assert "ValueError" in message
    assert "boom" in message


def test_handler_passes_the_parent_window() -> None:
    messagebox = MagicMock()
    root = object()

    handle_tk_callback_exception(
        *_raise_and_capture(RuntimeError("x")),
        messagebox_module=messagebox,
        parent=root,
    )

    assert messagebox.showerror.call_args.kwargs["parent"] is root


def test_handler_never_raises_when_the_dialog_fails() -> None:
    """It runs while the app is already failing; it must not add a second fault."""
    messagebox = MagicMock()
    messagebox.showerror.side_effect = RuntimeError("no display")

    handle_tk_callback_exception(
        *_raise_and_capture(ValueError("boom")), messagebox_module=messagebox
    )


def test_install_replaces_tk_default_handler() -> None:
    root = MagicMock()
    messagebox = MagicMock()

    install_tk_exception_handler(root, messagebox_module=messagebox)

    assert callable(root.report_callback_exception)
    root.report_callback_exception(*_raise_and_capture(KeyError("missing")))
    messagebox.showerror.assert_called_once()
    assert messagebox.showerror.call_args.kwargs["parent"] is root


def test_app_runner_installs_the_handler_before_building_the_ui() -> None:
    """Ordering matters: a callback firing before install is uncovered."""
    import inspect

    from zebtrack.core import app_runner

    source = inspect.getsource(app_runner.run_app)
    install_at = source.index("install_tk_exception_handler(root")
    first_use_at = source.index("_select_language_on_first_run")

    assert install_at < first_use_at
