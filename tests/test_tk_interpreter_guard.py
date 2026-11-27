"""Tests for tests/tk_interpreter_guard.py — the #735 guard.

``tkinter.Tcl()`` builds a real Tcl interpreter without Tk, so none of these
tests needs a display. Every interpreter created here is gone (or exempt) before
the test ends, otherwise the autouse guard in conftest.py would fail the test
itself — which is the guard working, not a bug in these tests.
"""

from __future__ import annotations

import gc
import subprocess
import sys
import textwrap
import tkinter
import weakref
from pathlib import Path
from typing import Any, cast

import pytest
import ttkbootstrap  # noqa: F401  (patches tkinter.Tk before any tracker does)
from ttkbootstrap.publisher import Channel, Publisher

from tests.tk_interpreter_guard import TkInterpreterTracker

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Cycle:
    """An object that keeps itself alive until the cyclic collector runs."""

    def __init__(self, interpreter: tkinter.Tk) -> None:
        self.me = self
        self.interpreter = interpreter


@pytest.fixture
def tracker():
    tracker = TkInterpreterTracker()
    tracker.install(tkinter.Tk)
    yield tracker
    tracker.uninstall()


def test_interpreter_left_in_a_cycle_is_reported_and_collected_on_the_calling_thread(tracker):
    gc.disable()  # no automatic collection may free it before the guard looks
    try:
        mark = tracker.mark()
        interpreter = tkinter.Tcl()
        ref = weakref.ref(interpreter)
        _Cycle(interpreter)
        del interpreter
        assert ref() is not None, "the cycle must keep the interpreter alive"

        leaks = tracker.leaks_since(mark)
    finally:
        gc.enable()

    assert ref() is None, "leaks_since must collect the cycle itself"
    assert len(leaks) == 1
    assert "reference cycle" in leaks[0]
    assert "test_tk_interpreter_guard.py" in leaks[0], leaks[0]


def test_interpreter_still_referenced_is_reported_with_its_creation_site(tracker):
    mark = tracker.mark()
    kept = tkinter.Tcl()

    leaks = tracker.leaks_since(mark)

    assert len(leaks) == 1
    assert "still referenced" in leaks[0]
    assert "kept = tkinter.Tcl()" in leaks[0], leaks[0]
    del kept


def test_interpreter_freed_inside_the_test_is_not_a_leak(tracker):
    mark = tracker.mark()
    interpreter = tkinter.Tcl()
    del interpreter

    assert tracker.leaks_since(mark) == []


def test_ttkbootstrap_registry_hold_is_released_not_reported(tracker):
    """ttkbootstrap keeps the newest root in its theme registry; that is not the test's leak."""
    mark = tracker.mark()
    interpreter = tkinter.Tcl()
    ref = weakref.ref(interpreter)
    del interpreter
    assert ref() is not None, "ttkbootstrap's registry is expected to hold the new root"
    held_before = Publisher.subscriber_count()

    assert tracker.leaks_since(mark) == []
    assert ref() is None, "releasing the registry entry must free the interpreter"
    assert Publisher.subscriber_count() == held_before - 1


def test_ttkbootstrap_entries_of_other_widgets_are_kept(tracker):
    survivor = object()
    Publisher.subscribe(name=".zz_guard_test", func=lambda w=survivor: w, channel=Channel.STD)
    try:
        mark = tracker.mark()
        interpreter = tkinter.Tcl()
        del interpreter

        assert tracker.leaks_since(mark) == []
        subscribers = cast(Any, Publisher).get_subscribers(Channel.STD)
        assert ".zz_guard_test" in [s.name for s in subscribers]
    finally:
        Publisher.unsubscribe(".zz_guard_test")


def test_interpreters_created_before_the_mark_are_not_blamed_on_the_test(tracker):
    earlier = tkinter.Tcl()
    mark = tracker.mark()

    assert tracker.leaks_since(mark) == []
    del earlier


def test_a_reported_leak_is_reported_once(tracker):
    mark = tracker.mark()
    kept = tkinter.Tcl()
    assert len(tracker.leaks_since(mark)) == 1

    assert tracker.leaks_since(tracker.mark()) == []
    assert tracker.leaks_since(mark) == []
    del kept


def test_exempt_interpreter_may_outlive_the_test(tracker):
    mark = tracker.mark()
    session_root = tkinter.Tcl()
    tracker.exempt(session_root)

    assert tracker.leaks_since(mark) == []
    del session_root


def test_uninstall_restores_the_original_constructor():
    original = tkinter.Tk.__init__
    tracker = TkInterpreterTracker()
    tracker.install(tkinter.Tk)
    assert tkinter.Tk.__init__ is not original
    assert tracker.installed

    tracker.uninstall()

    assert tkinter.Tk.__init__ is original
    assert not tracker.installed


def test_install_twice_wraps_once():
    original = tkinter.Tk.__init__
    tracker = TkInterpreterTracker()
    tracker.install(tkinter.Tk)
    wrapped = tkinter.Tk.__init__
    try:
        tracker.install(tkinter.Tk)
        assert tkinter.Tk.__init__ is wrapped
    finally:
        tracker.uninstall()
    assert tkinter.Tk.__init__ is original


def test_the_conftest_guard_fails_a_test_that_leaks_an_interpreter(tmp_path):
    """End to end: a leaking test errors at teardown, naming where it was created.

    Run in a child pytest so the deliberate leak never reaches this session.
    """
    test_file = tmp_path / "test_leaks_an_interpreter.py"
    test_file.write_text(
        textwrap.dedent(
            """
            import tkinter
            from unittest.mock import MagicMock

            RECORDER = MagicMock()


            def test_leaks():
                RECORDER(master=tkinter.Tcl())


            def test_clean():
                interpreter = tkinter.Tcl()
                del interpreter
            """
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            # The file lives outside tests/, so load the real conftest as a plugin.
            "-p",
            "tests.conftest",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-q",
            "-c",
            str(REPO_ROOT / "pytest.ini"),
            f"--rootdir={tmp_path}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode != 0, output
    # test_leaks' body passes; its teardown is the error. test_clean passes.
    assert "2 passed, 1 error" in output, output
    assert "ERROR at teardown of test_leaks" in output, output
    assert "Tcl/Tk interpreter" in output, output
    assert "RECORDER(master=tkinter.Tcl())" in output, output
