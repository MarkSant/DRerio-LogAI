"""Tests for MainViewModel.on_arduino_event threading marshaling.

The ArduinoManager reader thread calls this on the controller for inbound
external-trigger events; the recording coordinator it delegates to can create
Tk widgets (countdown Toplevel) or touch buttons/status, so dispatch must be
marshaled onto the main thread via root.after(0, ...) per CLAUDE.md.

Uses __new__ to avoid constructing the full DI graph — only ``root`` and
``hardware_vm`` are relevant to this method.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.core.main_view_model import MainViewModel


def _make_controller(*, root):
    controller = MainViewModel.__new__(MainViewModel)
    coordinator = MagicMock()
    controller.root = root
    controller.hardware_vm = cast(Any, SimpleNamespace(recording_session_coordinator=coordinator))
    return controller, coordinator


def test_marshals_via_root_after_when_root_present():
    root = MagicMock()
    controller, coordinator = _make_controller(root=root)

    controller.on_arduino_event(1)

    # Not called synchronously...
    coordinator.on_arduino_event.assert_not_called()
    # ...but scheduled on the Tk main loop.
    root.after.assert_called_once_with(0, coordinator.on_arduino_event, 1)


def test_falls_back_to_direct_call_when_no_root():
    controller, coordinator = _make_controller(root=None)

    controller.on_arduino_event(0)

    coordinator.on_arduino_event.assert_called_once_with(0)


def test_noop_when_coordinator_missing():
    root = MagicMock()
    controller, _coordinator = _make_controller(root=root)
    controller.hardware_vm = cast(Any, SimpleNamespace(recording_session_coordinator=None))

    controller.on_arduino_event(1)

    root.after.assert_not_called()
