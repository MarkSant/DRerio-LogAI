"""Run blocking work off the Tk thread and hand the result back to it.

Tk is single-threaded: a button handler that probes hardware or deletes a folder
freezes the whole window for as long as the call takes (audit A6,
``docs/audits/2026-11_A6_threads_tk.md``). ``run_in_background`` is the one
shape every such site uses:

- ``work()`` runs on a **daemon** thread (CLAUDE.md, "Threading & UI") and
  never touches Tk — not even ``after``: a cross-thread Tcl call needs the
  main loop to be running and raises ``RuntimeError`` otherwise;
- the Tk thread polls for the outcome with ``widget.after`` (scheduled from
  the Tk thread itself) and calls ``on_done(result)`` / ``on_error(exc)``
  there. They are never called from the worker;
- if the widget was destroyed while the work ran (dialog closed, wizard
  cancelled), the callbacks are dropped instead of touching a dead widget.

Threads are named ``ui-bg-<name>`` so tests can join them deterministically
before pumping the Tk event loop (``tests/utils/wait_helpers.drain_background_tasks``).
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

log = structlog.get_logger()

T = TypeVar("T")

THREAD_PREFIX = "ui-bg-"

# How often the Tk thread checks whether the worker finished. Short enough to
# feel immediate, long enough not to spin the event loop.
POLL_INTERVAL_MS = 50

# Tasks started but not yet delivered (or dropped), with the widget that owns
# them. Touched only on the Tk thread: added by ``run_in_background``, removed
# by the final poll.
_in_flight: dict[threading.Thread, Any] = {}


def pending_tasks() -> int:
    """How many tasks still owe the Tk thread a callback (for tests/diagnostics).

    A finished task whose widget is gone will never be polled again (its root
    was destroyed), so it is pruned instead of counted.
    """
    for thread, widget in list(_in_flight.items()):
        if not thread.is_alive() and not _widget_alive(widget):
            _in_flight.pop(thread, None)
    return len(_in_flight)


def _widget_alive(widget: Any) -> bool:
    """True when ``widget`` can still be configured (``winfo_exists`` is 1)."""
    try:
        return bool(widget.winfo_exists())
    except (tk.TclError, RuntimeError):
        return False


def run_in_background(
    widget: Any,
    work: Callable[[], T],
    on_done: Callable[[T], None],
    on_error: Callable[[BaseException], None] | None = None,
    *,
    name: str,
) -> threading.Thread:
    """Run ``work`` on a daemon thread; deliver its outcome on the Tk thread.

    Must be called on the Tk thread (it schedules the first poll).

    Args:
        widget: Any Tk widget (or root) that owns the callbacks; its ``after``
            schedules the polls and its ``winfo_exists`` decides whether the
            callbacks still make sense.
        work: The blocking call. Must not touch Tk.
        on_done: Receives ``work()``'s return value, on the Tk thread.
        on_error: Receives the exception ``work()`` raised, on the Tk thread.
            Without it the exception is only logged.
        name: Short label for the thread name and the log events.

    Returns:
        The started thread (already running).
    """
    outcome: dict[str, Any] = {}

    def _run() -> None:
        try:
            outcome["result"] = work()
        # except Exception justified: the worker must always report back, and
        # whatever ``work`` raises is handed to ``on_error`` on the Tk thread.
        except Exception as exc:
            log.warning("ui.background_task.failed", task=name, error=str(exc))
            outcome["error"] = exc

    thread = threading.Thread(target=_run, name=f"{THREAD_PREFIX}{name}", daemon=True)

    def _poll() -> None:
        if thread.is_alive():
            _schedule_poll()
            return
        _in_flight.pop(thread, None)
        if not _widget_alive(widget):
            log.debug("ui.background_task.widget_gone", task=name)
            return
        if "error" in outcome:
            if on_error is not None:
                on_error(outcome["error"])
            return
        on_done(outcome["result"])

    def _schedule_poll() -> None:
        try:
            widget.after(POLL_INTERVAL_MS, _poll)
        except (tk.TclError, RuntimeError) as exc:
            # Root destroyed: nobody is left to show the result.
            _in_flight.pop(thread, None)
            log.debug("ui.background_task.after_failed", task=name, error=str(exc))

    _in_flight[thread] = widget
    thread.start()
    _schedule_poll()
    return thread
