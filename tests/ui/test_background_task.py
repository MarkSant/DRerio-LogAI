"""Thread contract of ``zebtrack.ui.background_task.run_in_background`` (audit A6).

The helper exists so a Tk handler can push blocking work (camera enumeration,
port scans, deletes) to a daemon thread. What makes it correct is not that the
work runs, but WHERE each piece runs:

- ``work`` on a daemon worker thread, never on the caller's thread;
- ``on_done``/``on_error`` on the Tk thread, and only from an ``after``
  callback — never from the worker.

A MagicMock widget would hide the difference (``after`` records the call and
never runs it), so ``_DeferringWidget`` QUEUES ``after`` callbacks and the test
decides when the "Tk loop" turns.
"""

from __future__ import annotations

import threading
import tkinter as tk

import pytest
from tests.utils.deferring_tk import DeferringTk

from zebtrack.ui import background_task
from zebtrack.ui.background_task import THREAD_PREFIX, pending_tasks, run_in_background


class _DeferringWidget(DeferringTk):
    """``DeferringTk`` plus a helper that waits for one worker, then drains."""

    def turn_until_delivered(self, worker: threading.Thread, timeout: float = 5.0) -> None:
        worker.join(timeout)
        assert not worker.is_alive()
        self.run_until_idle(timeout)


@pytest.fixture(autouse=True)
def _clean_registry():
    background_task._in_flight.clear()
    yield
    background_task._in_flight.clear()


def test_work_runs_on_a_named_daemon_thread_and_result_waits_for_the_tk_loop():
    widget = _DeferringWidget()
    seen: dict = {}
    release = threading.Event()

    def work():
        seen["work_thread"] = threading.current_thread()
        release.wait(5)
        return 42

    def on_done(value):
        seen["done_thread"] = threading.current_thread()
        seen["value"] = value

    worker = run_in_background(widget, work, on_done, name="probe")

    assert worker.daemon is True
    assert worker.name == f"{THREAD_PREFIX}probe"
    release.set()
    worker.join(5)

    # The worker finished, but nothing was delivered: the Tk loop has not turned.
    assert "value" not in seen
    assert pending_tasks() == 1

    widget.turn_until_delivered(worker)

    assert seen["value"] == 42
    assert seen["work_thread"] is worker
    assert seen["work_thread"] is not threading.main_thread()
    assert seen["done_thread"] is threading.main_thread()
    assert pending_tasks() == 0


def test_the_worker_never_calls_after():
    """A cross-thread ``after`` needs the main loop running; the worker stays off Tk."""
    widget = _DeferringWidget()
    worker = run_in_background(widget, lambda: "x", lambda _v: None, name="probe")

    widget.turn_until_delivered(worker)

    assert widget.after_threads
    assert all(t is threading.main_thread() for t in widget.after_threads)


def test_poll_reschedules_while_the_worker_is_still_running():
    widget = _DeferringWidget()
    release = threading.Event()
    delivered: list = []

    worker = run_in_background(
        widget, lambda: release.wait(5) and "late", delivered.append, name="slow"
    )

    # One poll while the worker is blocked: it must re-arm, not deliver.
    first_polls, widget.pending = widget.pending, []
    for poll in first_polls:
        poll()
    assert delivered == []
    assert len(widget.pending) == 1

    release.set()
    widget.turn_until_delivered(worker)
    assert delivered == ["late"]


def test_error_goes_to_on_error_on_the_tk_thread_and_on_done_is_not_called():
    widget = _DeferringWidget()
    boom = OSError("camera busy")
    errors: list = []
    done: list = []

    def work():
        raise boom

    def on_error(exc):
        errors.append((exc, threading.current_thread()))

    worker = run_in_background(widget, work, done.append, on_error, name="fails")
    worker.join(5)
    assert errors == []

    widget.turn_until_delivered(worker)

    assert errors == [(boom, threading.main_thread())]
    assert done == []
    assert pending_tasks() == 0


def test_error_without_on_error_is_dropped_quietly():
    widget = _DeferringWidget()
    done: list = []

    def work():
        raise ValueError("nope")

    worker = run_in_background(widget, work, done.append, name="fails")
    widget.turn_until_delivered(worker)

    assert done == []
    assert pending_tasks() == 0


def test_destroyed_widget_drops_the_callbacks():
    widget = _DeferringWidget()
    done: list = []
    worker = run_in_background(widget, lambda: 1, done.append, name="closed")
    worker.join(5)

    widget.alive = False  # dialog closed while the worker ran
    widget.turn_until_delivered(worker)

    assert done == []
    assert pending_tasks() == 0


def test_after_failure_drops_the_task_without_raising():
    class _DeadRoot(_DeferringWidget):
        def after(self, _delay, _callback):
            raise tk.TclError("application has been destroyed")

    widget = _DeadRoot()
    worker = run_in_background(widget, lambda: 1, lambda _v: None, name="dead")
    worker.join(5)

    assert pending_tasks() == 0


def test_pending_tasks_prunes_finished_tasks_whose_widget_is_gone():
    widget = _DeferringWidget()
    worker = run_in_background(widget, lambda: 1, lambda _v: None, name="orphan")
    worker.join(5)
    assert pending_tasks() == 1

    # The root was destroyed: its queued poll will never run.
    widget.alive = False
    assert pending_tasks() == 0


def test_pending_tasks_keeps_a_running_task_even_if_its_widget_is_gone():
    widget = _DeferringWidget()
    release = threading.Event()
    worker = run_in_background(widget, lambda: release.wait(5), lambda _v: None, name="busy")

    widget.alive = False
    assert pending_tasks() == 1

    release.set()
    worker.join(5)
    assert pending_tasks() == 0
