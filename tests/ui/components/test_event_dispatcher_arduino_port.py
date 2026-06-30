"""Tests for the immediate Arduino reconnect on port change (EventDispatcher)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.ui.components.event_dispatcher import EventDispatcher


def _make_dispatcher(*, connect_result=True):
    manager = MagicMock()
    manager.connect.return_value = connect_result
    settings = SimpleNamespace(arduino=SimpleNamespace(baud_rate=9600, handshake="none"))
    dashboard = MagicMock()
    controller = SimpleNamespace(arduino_manager=manager, settings=settings)
    # A non-EventBus context (has ``event_bus`` attr) is treated as the GUI.
    gui = SimpleNamespace(event_bus=None, controller=controller, arduino_dashboard_widget=dashboard)
    dispatcher = EventDispatcher(cast(Any, gui))
    return dispatcher, manager, dashboard


def test_port_update_reconnects_with_settings():
    dispatcher, manager, dashboard = _make_dispatcher(connect_result=True)
    dispatcher._handle_arduino_port_update({"port": "COM4", "old_port": "COM3"})

    manager.connect.assert_called_once_with("COM4", 9600, handshake="none")
    dashboard.update_status.assert_called_once_with(connected=True, port="COM4")


def test_port_update_failure_reports_disconnected():
    dispatcher, manager, dashboard = _make_dispatcher(connect_result=False)
    dispatcher._handle_arduino_port_update({"port": "COM9"})

    manager.connect.assert_called_once()
    dashboard.update_status.assert_called_once_with(connected=False, port=None)


def test_empty_port_is_ignored():
    dispatcher, manager, dashboard = _make_dispatcher()
    dispatcher._handle_arduino_port_update({"port": ""})

    manager.connect.assert_not_called()
    dashboard.update_status.assert_not_called()


def test_connect_exception_reports_disconnected():
    dispatcher, manager, dashboard = _make_dispatcher()
    manager.connect.side_effect = OSError("port busy")
    dispatcher._handle_arduino_port_update({"port": "COM4"})

    dashboard.update_status.assert_called_once_with(connected=False, port=None)
