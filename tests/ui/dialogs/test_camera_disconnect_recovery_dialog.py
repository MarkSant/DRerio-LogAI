"""Tests for CameraDisconnectRecoveryDialog.

The dialog appears when the camera drops during a live recording. What the
researcher sees and what the dialog tells the live service are asserted through
the real handlers: the countdown label, the buttons, and the action handed to
``on_action_callback``.

Two things are deliberately NOT done here:

* no real timers: ``after`` is replaced on the instance by a recorder, so the
  countdown advances only when a test calls ``_update_countdown``;
* no sleeps as synchronisation: the "wait" action runs its callback in a thread,
  which these tests start through a recording subclass and join.
"""

from __future__ import annotations

import threading
import tkinter as tk
import types
from tkinter import ttk
from typing import Any, ClassVar

import pytest
import structlog

from zebtrack.i18n import _
from zebtrack.ui.dialogs import camera_disconnect_recovery_dialog as dialog_module
from zebtrack.ui.dialogs.camera_disconnect_recovery_dialog import (
    CameraDisconnectRecoveryDialog,
)


class _AfterRecorder:
    """Stand-in for ``Misc.after``: records what was scheduled, runs nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, Any]] = []

    def __call__(self, delay: int, func: Any = None, *args: Any) -> str:
        self.calls.append((delay, func))
        return f"after#{len(self.calls)}"

    def scheduled(self, delay: int) -> list[Any]:
        return [func for scheduled_delay, func in self.calls if scheduled_delay == delay]


class _RecordingThread(threading.Thread):
    """Real thread, remembered so a test can join it (no sleeps)."""

    started: ClassVar[list[_RecordingThread]] = []

    def start(self) -> None:
        type(self).started.append(self)
        super().start()


@pytest.fixture
def worker_threads(monkeypatch: pytest.MonkeyPatch) -> list[_RecordingThread]:
    """Make the dialog's ``threading.Thread`` observable, only inside its module."""
    _RecordingThread.started = []
    monkeypatch.setattr(
        dialog_module,
        "threading",
        types.SimpleNamespace(Thread=_RecordingThread),
    )
    return _RecordingThread.started


def _join_all(threads: list[_RecordingThread]) -> None:
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive(), "worker thread did not finish"


def _build(
    root: tk.Misc,
    callback: Any = None,
    *,
    gap_duration_s: float = 12.5,
    experiment_id: str = "CECT_4",
) -> tuple[CameraDisconnectRecoveryDialog, _AfterRecorder, list[str]]:
    actions: list[str] = []

    def default_callback(action: str) -> None:
        actions.append(action)

    dialog = CameraDisconnectRecoveryDialog(
        parent=root,
        gap_duration_s=gap_duration_s,
        experiment_id=experiment_id,
        on_action_callback=callback if callback is not None else default_callback,
    )
    recorder = _AfterRecorder()
    dialog.after = recorder  # type: ignore[method-assign, assignment]
    return dialog, recorder, actions


def _walk(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_walk(child))
    return found


def _button(dialog: tk.Misc, text: str) -> ttk.Button:
    for widget in _walk(dialog):
        if isinstance(widget, ttk.Button) and str(widget.cget("text")) == text:
            return widget
    raise AssertionError(f"no button labelled {text!r}")


def _label_texts(dialog: tk.Misc) -> list[str]:
    return [str(w.cget("text")) for w in _walk(dialog) if isinstance(w, ttk.Label)]


def _close_via_window_manager(dialog: tk.Toplevel) -> None:
    """Fire the WM_DELETE_WINDOW protocol exactly as the title-bar X does."""
    dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))


FAILED_TEXT = "The reconnection request failed. Choose how to continue."


@pytest.mark.gui
class TestWhatTheResearcherSees:
    def test_description_names_the_session_and_rounds_the_gap_to_one_decimal(self, tkinter_root):
        dialog, _after, _actions = _build(
            tkinter_root, gap_duration_s=3.14159, experiment_id="CECT_4"
        )

        description = next(t for t in _label_texts(dialog) if "CECT_4" in t)

        assert "session 'CECT_4'" in description
        assert "after 3.1s without valid frames" in description
        assert "3.14" not in description

    def test_countdown_starts_at_30_seconds_with_a_full_bar(self, tkinter_root):
        dialog, _after, _actions = _build(tkinter_root)

        assert dialog.countdown_label.cget("text") == "Trying to reconnect automatically in 30s..."
        assert float(dialog.progress.cget("value")) == 30.0
        assert float(dialog.progress.cget("maximum")) == 30.0

    def test_the_wait_button_is_disabled_because_waiting_is_automatic(self, tkinter_root):
        dialog, _after, _actions = _build(tkinter_root)

        assert str(dialog.wait_btn.cget("state")) == "disabled"

    def test_the_window_is_modal_and_titled(self, tkinter_root):
        dialog, _after, _actions = _build(tkinter_root)

        assert dialog.title() == "Camera Disconnected"
        assert dialog.grab_current() == dialog


@pytest.mark.gui
class TestCountdown:
    def test_each_tick_shows_the_remaining_seconds_and_schedules_the_next_in_one_second(
        self, tkinter_root
    ):
        dialog, after, _actions = _build(tkinter_root)
        # __init__ already rendered 30 and decremented to 29.
        assert dialog.countdown_remaining == 29

        dialog._update_countdown()

        assert dialog.countdown_label.cget("text") == "Trying to reconnect automatically in 29s..."
        assert float(dialog.progress.cget("value")) == 29.0
        assert dialog.countdown_remaining == 28
        assert after.calls == [(1000, dialog._update_countdown)]

    def test_reaching_zero_hands_the_decision_to_the_wait_action(
        self, tkinter_root, worker_threads
    ):
        dialog, after, actions = _build(tkinter_root)
        dialog.countdown_remaining = 0

        dialog._update_countdown()
        _join_all(worker_threads)

        assert actions == ["wait"]
        assert dialog.action_taken is True
        assert dialog.countdown_active is False
        assert after.calls == [], "no further tick may be scheduled after the timeout"

    def test_a_tick_after_the_countdown_was_stopped_does_nothing(self, tkinter_root):
        dialog, after, _actions = _build(tkinter_root)
        dialog.countdown_active = False
        before = dialog.countdown_remaining
        label_before = dialog.countdown_label.cget("text")

        dialog._update_countdown()

        assert dialog.countdown_remaining == before
        assert dialog.countdown_label.cget("text") == label_before
        assert after.calls == []


@pytest.mark.gui
class TestUserActions:
    def test_resume_reports_resume_once_and_closes_the_dialog(self, tkinter_root):
        dialog, _after, actions = _build(tkinter_root)

        _button(dialog, _("🔌 Resume Manually")).invoke()

        assert actions == ["resume"]
        assert not dialog.winfo_exists()

    def test_stop_reports_stop_once_and_closes_the_dialog(self, tkinter_root):
        dialog, _after, actions = _build(tkinter_root)

        _button(dialog, _("⏹️ Stop Session")).invoke()

        assert actions == ["stop"]
        assert not dialog.winfo_exists()

    def test_closing_the_window_counts_as_stop(self, tkinter_root):
        dialog, _after, actions = _build(tkinter_root)

        _close_via_window_manager(dialog)

        assert actions == ["stop"]
        assert not dialog.winfo_exists()

    def test_a_second_action_after_the_first_is_ignored(self, tkinter_root, worker_threads):
        dialog, _after, actions = _build(tkinter_root)

        dialog._on_wait()
        _join_all(worker_threads)
        dialog._on_resume()
        dialog._on_stop()

        assert actions == ["wait"]
        assert dialog.winfo_exists(), "wait keeps the dialog open to show its status"

    def test_wait_stops_the_countdown_and_says_it_is_waiting(self, tkinter_root, worker_threads):
        dialog, _after, actions = _build(tkinter_root)

        dialog._on_wait()
        _join_all(worker_threads)

        assert actions == ["wait"]
        assert dialog.countdown_active is False
        assert dialog.countdown_label.cget("text") == "Waiting for the camera to reconnect..."

    def test_wait_runs_the_callback_off_the_ui_thread_in_a_daemon_thread(
        self, tkinter_root, worker_threads
    ):
        seen: list[tuple[str, int]] = []

        def callback(action: str) -> None:
            seen.append((action, threading.get_ident()))

        dialog, _after, _actions = _build(tkinter_root, callback)

        dialog._on_wait()
        _join_all(worker_threads)

        assert len(worker_threads) == 1
        assert worker_threads[0].daemon is True
        assert seen[0][0] == "wait"
        assert seen[0][1] != threading.get_ident()

    def test_resume_and_stop_do_not_start_a_thread(self, tkinter_root, worker_threads):
        dialog, _after, _actions = _build(tkinter_root)
        dialog._on_resume()

        dialog2, _after2, _actions2 = _build(tkinter_root)
        dialog2._on_stop()

        assert worker_threads == []


@pytest.mark.gui
class TestACallbackThatRaises:
    """A5-S-009: a failing callback used to leave the dialog latched.

    ``action_taken`` stayed True, so every button became a silent no-op while the
    label kept saying "Waiting for the camera to reconnect...".
    """

    @staticmethod
    def _failing_once(action_to_fail: str) -> tuple[Any, list[str]]:
        calls: list[str] = []

        def callback(action: str) -> None:
            calls.append(action)
            if action == action_to_fail and calls.count(action_to_fail) == 1:
                raise RuntimeError("event bus is down")

        return callback, calls

    def test_a_failing_wait_is_logged_with_the_action_and_session(
        self, tkinter_root, worker_threads
    ):
        callback, _calls = self._failing_once("wait")
        dialog, _after, _actions = _build(tkinter_root, callback, experiment_id="CECT_4")

        with structlog.testing.capture_logs() as logs:
            dialog._on_wait()
            _join_all(worker_threads)

        failures = [e for e in logs if e["event"] == "camera_disconnect_dialog.callback.failed"]
        assert len(failures) == 1
        assert failures[0]["action"] == "wait"
        assert failures[0]["experiment_id"] == "CECT_4"
        assert failures[0]["log_level"] == "error"

    def test_a_failing_wait_restores_the_dialog_through_after_zero(
        self, tkinter_root, worker_threads
    ):
        callback, _calls = self._failing_once("wait")
        dialog, after, _actions = _build(tkinter_root, callback)

        dialog._on_wait()
        _join_all(worker_threads)

        # The worker thread must not touch Tk itself: it only schedules the repair.
        assert dialog.action_taken is True
        pending = after.scheduled(0)
        assert len(pending) == 1
        pending[0]()

        assert dialog.action_taken is False
        assert dialog.countdown_label.cget("text") == FAILED_TEXT
        assert str(dialog.wait_btn.cget("state")) == "normal"

    def test_after_a_failed_wait_resume_works(self, tkinter_root, worker_threads):
        callback, calls = self._failing_once("wait")
        dialog, after, _actions = _build(tkinter_root, callback)
        dialog._on_wait()
        _join_all(worker_threads)
        after.scheduled(0)[0]()

        _button(dialog, _("🔌 Resume Manually")).invoke()

        assert calls == ["wait", "resume"]
        assert not dialog.winfo_exists()

    def test_after_a_failed_wait_the_user_can_retry_waiting(self, tkinter_root, worker_threads):
        callback, calls = self._failing_once("wait")
        dialog, after, _actions = _build(tkinter_root, callback)
        dialog._on_wait()
        _join_all(worker_threads)
        after.scheduled(0)[0]()

        dialog.wait_btn.invoke()
        _join_all(worker_threads)

        assert calls == ["wait", "wait"]
        assert dialog.countdown_label.cget("text") == "Waiting for the camera to reconnect..."

    def test_a_failing_resume_keeps_the_dialog_open_and_usable(self, tkinter_root):
        callback, calls = self._failing_once("resume")
        dialog, _after, _actions = _build(tkinter_root, callback)

        with structlog.testing.capture_logs() as logs:
            _button(dialog, _("🔌 Resume Manually")).invoke()

        assert dialog.winfo_exists()
        assert dialog.action_taken is False
        assert dialog.countdown_label.cget("text") == FAILED_TEXT
        assert [
            e["action"] for e in logs if e["event"] == "camera_disconnect_dialog.callback.failed"
        ] == ["resume"]

        _button(dialog, _("⏹️ Stop Session")).invoke()

        assert calls == ["resume", "stop"]
        assert not dialog.winfo_exists()

    def test_a_failing_stop_keeps_the_dialog_open_so_the_window_can_be_closed_again(
        self, tkinter_root
    ):
        callback, calls = self._failing_once("stop")
        dialog, _after, _actions = _build(tkinter_root, callback)

        _close_via_window_manager(dialog)
        assert dialog.winfo_exists()

        _close_via_window_manager(dialog)

        assert calls == ["stop", "stop"]
        assert not dialog.winfo_exists()

    def test_the_repair_is_harmless_when_the_dialog_was_closed_meanwhile(
        self, tkinter_root, worker_threads
    ):
        callback, _calls = self._failing_once("wait")
        dialog, after, _actions = _build(tkinter_root, callback)
        dialog._on_wait()
        _join_all(worker_threads)
        repair = after.scheduled(0)[0]
        dialog.destroy()

        repair()  # must not raise TclError on a destroyed widget

        assert not dialog.winfo_exists()

    def test_a_dialog_destroyed_before_the_failure_does_not_crash_the_worker(
        self, tkinter_root, worker_threads
    ):
        callback, _calls = self._failing_once("wait")
        dialog, _after, _actions = _build(tkinter_root, callback)

        def refuse(*_args: Any) -> str:
            raise tk.TclError('can\'t invoke "after" command: application has been destroyed')

        dialog.after = refuse  # type: ignore[method-assign, assignment]
        hook_calls: list[Any] = []
        original_hook = threading.excepthook
        threading.excepthook = hook_calls.append
        try:
            dialog._on_wait()
            _join_all(worker_threads)
        finally:
            threading.excepthook = original_hook

        assert hook_calls == [], "the worker must swallow the TclError, not die with it"


class _StubWidget:
    """Records ``config`` calls; the stand-in for a label or button."""

    def __init__(self) -> None:
        self.configs: list[dict[str, Any]] = []

    def config(self, **kwargs: Any) -> None:
        self.configs.append(kwargs)


class TestDecisionsWithoutTk:
    """The dialog's decisions, driven on a Tk-free instance.

    These run in the fast suite (and are what ``scripts/mutation_check.py`` can
    see: it deselects ``gui`` tests). ``object.__new__`` skips the Toplevel
    constructor; every assertion is on what a REAL method of the dialog does to
    the widgets, the callback and the scheduler.
    """

    @staticmethod
    def _stub(callback: Any) -> tuple[Any, dict[str, Any]]:
        dialog = object.__new__(CameraDisconnectRecoveryDialog)
        seen: dict[str, Any] = {"destroyed": 0, "after": []}
        dialog.experiment_id = "CECT_4"
        dialog.on_action_callback = callback
        dialog.action_taken = False
        dialog.countdown_active = True
        dialog.countdown_remaining = 30
        dialog.countdown_label = _StubWidget()  # type: ignore[assignment]
        dialog.wait_btn = _StubWidget()  # type: ignore[assignment]
        dialog.progress = _StubWidget()  # type: ignore[assignment]
        dialog.winfo_exists = lambda: True  # type: ignore[method-assign]
        dialog.destroy = lambda: seen.__setitem__("destroyed", seen["destroyed"] + 1)  # type: ignore[method-assign]
        dialog.after = lambda delay, func=None, *a: seen["after"].append((delay, func))  # type: ignore[method-assign]
        return dialog, seen

    @staticmethod
    def _failing(action_to_fail: str) -> tuple[Any, list[str]]:
        calls: list[str] = []

        def callback(action: str) -> None:
            calls.append(action)
            if action == action_to_fail:
                raise RuntimeError("event bus is down")

        return callback, calls

    @pytest.mark.parametrize("action", ["resume", "stop"])
    def test_a_successful_synchronous_action_reports_it_and_closes(self, action):
        calls: list[str] = []
        dialog, seen = self._stub(calls.append)

        getattr(dialog, f"_on_{action}")()

        assert calls == [action]
        assert seen["destroyed"] == 1
        assert dialog.action_taken is True
        assert dialog.countdown_active is False

    @pytest.mark.parametrize("action", ["resume", "stop"])
    def test_a_failing_synchronous_action_leaves_the_dialog_open_and_usable(self, action):
        callback, calls = self._failing(action)
        dialog, seen = self._stub(callback)

        getattr(dialog, f"_on_{action}")()

        assert calls == [action]
        assert seen["destroyed"] == 0
        assert dialog.action_taken is False
        assert dialog.countdown_label.configs == [{"text": FAILED_TEXT, "foreground": "red"}]
        assert dialog.wait_btn.configs == [{"state": tk.NORMAL}]

    def test_a_failing_wait_is_repaired_only_through_after_zero(self, worker_threads):
        callback, calls = self._failing("wait")
        dialog, seen = self._stub(callback)

        dialog._on_wait()
        _join_all(worker_threads)

        assert calls == ["wait"]
        assert worker_threads[0].daemon is True
        assert dialog.action_taken is True, "the worker thread must not repair widgets itself"
        assert [delay for delay, _func in seen["after"]] == [0]

        seen["after"][0][1]()

        assert dialog.action_taken is False
        assert dialog.countdown_label.configs[-1] == {"text": FAILED_TEXT, "foreground": "red"}
        assert dialog.wait_btn.configs == [{"state": tk.NORMAL}]

    def test_the_repair_does_nothing_once_the_window_is_gone(self):
        dialog, _seen = self._stub(lambda action: None)
        dialog.action_taken = True
        dialog.winfo_exists = lambda: False  # type: ignore[method-assign]

        dialog._restore_after_callback_failure()

        assert dialog.action_taken is True
        assert dialog.countdown_label.configs == []

    def test_the_countdown_expires_at_zero_not_before(self, worker_threads):
        calls: list[str] = []
        dialog, seen = self._stub(calls.append)
        dialog.countdown_remaining = 1

        dialog._update_countdown()

        assert calls == []
        assert dialog.countdown_remaining == 0
        assert dialog.progress.configs == [{"value": 1}]
        assert dialog.countdown_label.configs == [
            {"text": "Trying to reconnect automatically in 1s..."}
        ]
        assert [delay for delay, _func in seen["after"]] == [1000]

        dialog._update_countdown()
        _join_all(worker_threads)

        assert calls == ["wait"]
        assert [delay for delay, _func in seen["after"]] == [1000]
