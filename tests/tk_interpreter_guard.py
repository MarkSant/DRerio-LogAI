"""Guard: no test may leave a Tcl/Tk interpreter for the garbage collector (#735).

A ``tkinter.Tk`` (and ``tkinter.Tcl()``, which is a ``Tk`` built with
``useTk=False``) owns a Tcl interpreter. Freeing that interpreter on any thread
other than the one that created it makes Tcl abort the whole process::

    Tcl_AsyncDelete: async handler deleted by the wrong thread
    Fatal Python error: Aborted

That is true even after ``root.destroy()``: ``destroy`` removes the window, the
interpreter is only deleted when the Python object is freed. An interpreter
caught in a reference cycle (a ``MagicMock`` recording it in ``call_args`` is
enough) is freed by the cyclic garbage collector, and the collector runs on
whichever thread happens to allocate when a collection is due. In the suite that
is often a worker thread: the nightly "3x full suite" job died every night of
November 2026 inside ``Camera._reader_thread`` in ``tests/io/test_camera.py``,
collecting an interpreter that ``ROITemplateManager`` had created hundreds of
tests earlier with a private ``Tcl()`` fallback.

The crash names the thread that happened to collect, never the test that leaked,
so the guard checks at the end of every test instead: an interpreter created by
the test that is still alive at teardown is collected *here*, on the main thread,
and the test fails with the creation site. The session root created by
``tkinter_session_root`` is exempt — it is meant to outlive the tests.
"""

from __future__ import annotations

import functools
import gc
import os
import sys
import sysconfig
import traceback
import weakref
from collections.abc import Callable
from typing import Any

_STDLIB = os.path.normcase(sysconfig.get_paths()["stdlib"])


def _is_noise(filename: str) -> bool:
    """Frames of the stdlib (tkinter, runpy), installed packages and this module."""
    path = os.path.normcase(filename)
    return (
        filename.startswith("<")
        or path.startswith(_STDLIB)
        or "site-packages" in path
        or os.path.basename(path) == "tk_interpreter_guard.py"
    )


def _creation_site() -> str:
    """The project frames (src/ and tests/) that led to the new interpreter."""
    frames = [frame for frame in traceback.extract_stack() if not _is_noise(frame.filename)]
    return "".join(traceback.format_list(frames[-6:])).rstrip()


def _release_ttkbootstrap_hold(root: Any) -> None:
    """Drop the reference ttkbootstrap's theme ``Publisher`` keeps to ``root``.

    Once ttkbootstrap is imported it wraps ``tkinter.Tk.__init__`` and subscribes
    every new root to a process-wide registry keyed by Tcl name — always ``"."``
    for a root — so the newest root stays referenced until the next one replaces
    it. That hold is released on the main thread and is not what the guard looks
    for, but it would hide whether the TEST let go of its interpreter. Only an
    entry whose widget is ``root`` itself is removed.
    """
    publisher_module = sys.modules.get("ttkbootstrap.publisher")
    publisher = getattr(publisher_module, "Publisher", None)
    subscribers = getattr(publisher, "_Publisher__subscribers", None)
    if not isinstance(subscribers, dict):
        return
    for name, subscriber in list(subscribers.items()):
        defaults = getattr(getattr(subscriber, "func", None), "__defaults__", None) or ()
        if any(value is root for value in defaults):
            del subscribers[name]


class TkInterpreterTracker:
    """Records every ``tkinter.Tk`` built while installed, by weak reference."""

    def __init__(self) -> None:
        self._created: list[tuple[weakref.ref[Any], str]] = []
        self._exempt: list[weakref.ref[Any]] = []
        self._original_init: Callable[..., None] | None = None
        self._tk_class: Any = None

    @property
    def installed(self) -> bool:
        return self._original_init is not None

    def install(self, tk_class: Any) -> None:
        """Wrap ``tk_class.__init__`` so each new interpreter is recorded."""
        if self.installed:
            return
        original = tk_class.__init__
        created = self._created

        @functools.wraps(original)
        def recording_init(root: Any, *args: Any, **kwargs: Any) -> None:
            original(root, *args, **kwargs)
            created.append((weakref.ref(root), _creation_site()))

        self._tk_class = tk_class
        self._original_init = original
        tk_class.__init__ = recording_init

    def uninstall(self) -> None:
        if self._original_init is None:
            return
        self._tk_class.__init__ = self._original_init
        self._original_init = None
        self._tk_class = None

    def exempt(self, root: Any) -> None:
        """Allow ``root`` to outlive the test that created it (the session root)."""
        self._exempt.append(weakref.ref(root))

    def mark(self) -> int:
        """Position to pass to :meth:`leaks_since` once the test is over."""
        return len(self._created)

    def _is_exempt(self, root: Any) -> bool:
        return any(ref() is root for ref in self._exempt)

    def leaks_since(self, mark: int) -> list[str]:
        """Interpreters created after ``mark`` that the test left alive.

        Each one is collected on the calling (main) thread before this returns,
        when it can be: the point is that it never reaches a worker thread's
        collection. Returns one description per leak, with its creation site;
        an empty list means the test cleaned up after itself.
        """
        pending = []
        for ref, site in self._created[mark:]:
            root = ref()
            if root is None or self._is_exempt(root):
                continue
            _release_ttkbootstrap_hold(root)
            del root
            # Dropping the registry entry may have been the last reference.
            if ref() is not None:
                pending.append((ref, site))
        del self._created[mark:]
        if not pending:
            return []
        gc.collect()
        leaks = []
        for ref, site in pending:
            if ref() is None:
                fate = "was left in a reference cycle (freed only by this gc.collect())"
            else:
                fate = "is still referenced after the test (will be freed by an unknown thread)"
            leaks.append(f"a Tcl/Tk interpreter {fate}, created at:\n{site}")
        return leaks
