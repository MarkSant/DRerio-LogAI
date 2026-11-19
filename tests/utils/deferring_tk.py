"""A Tk stand-in that makes "was this marshalled to the Tk thread?" observable.

A MagicMock widget swallows the difference between a handler that touches Tk
directly and one that marshals correctly: ``after(0, cb)`` is recorded and ``cb``
never runs. ``DeferringTk`` QUEUES ``after`` callbacks and lets the test turn
the "Tk loop" explicitly, recording which thread scheduled and which ran each
callback. Used by the A6 thread-contract tests (``ui.background_task`` sites).
"""

from __future__ import annotations

import threading
import time
from typing import Any


class DeferringTk:
    """``after``/``winfo_exists`` stub with an explicit, test-driven event loop."""

    def __init__(self) -> None:
        self.pending: list = []
        self.after_threads: list[threading.Thread] = []
        #: Every ``after`` request as ``(delay, callback)``, in order.
        self.scheduled: list[tuple[Any, Any]] = []
        self.alive = True

    def after(self, _delay, callback=None, *args):
        self.after_threads.append(threading.current_thread())
        self.scheduled.append((_delay, callback))
        if callback is not None:
            self.pending.append(lambda: callback(*args))
        return f"after#{len(self.after_threads)}"

    def after_cancel(self, _after_id) -> None:
        return None

    def winfo_exists(self) -> int:
        return 1 if self.alive else 0

    def run_pending(self) -> None:
        """Run what is queued right now (one turn of the loop)."""
        pending, self.pending = self.pending, []
        for callback in pending:
            callback()

    def run_until_idle(self, timeout: float = 5.0) -> None:
        """Turn the loop until nothing is queued (background polls included)."""
        deadline = time.monotonic() + timeout
        while self.pending:
            assert time.monotonic() < deadline, "after-queue never drained"
            self.run_pending()
            time.sleep(0.001)


def bind_deferring_tk(obj, tk: DeferringTk | None = None) -> DeferringTk:
    """Route ``obj.after``/``obj.winfo_exists`` to a ``DeferringTk`` and return it."""
    tk = tk or DeferringTk()
    obj.after = tk.after
    obj.after_cancel = tk.after_cancel
    obj.winfo_exists = tk.winfo_exists
    return tk
