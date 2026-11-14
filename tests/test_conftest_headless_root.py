"""The headless Tk root in tests/conftest.py must behave like a root.

Without a display (ZEBTRACK_HEADLESS_TESTS=1, or a CI job run without xvfb) the
``tkinter_session_root`` fixture hands out ``_create_mock_tk_root()`` instead of a
real ``tk.Tk``. Widgets built on it call ``tkinter.Misc._root()``, which climbs
``.master`` until it finds ``None``. A MagicMock never yields ``None`` on its own,
so the climb never ended and the nightly memory job died on pytest-timeout.
"""

from __future__ import annotations

import tkinter
from unittest.mock import MagicMock

from tests.conftest import _create_mock_tk_root


def test_headless_root_has_no_master():
    root = _create_mock_tk_root()

    assert root.master is None


def test_root_lookup_from_a_child_widget_stops_at_the_headless_root():
    root = _create_mock_tk_root()
    toplevel = MagicMock()
    toplevel.master = root
    widget = MagicMock()
    widget.master = toplevel

    assert tkinter.Misc._root(widget) is root  # type: ignore[attr-defined]
