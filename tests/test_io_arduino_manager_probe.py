"""Tests for ``ArduinoManager.probe_tokens`` — the bindings pre-flight check.

The probe sends each configured token and reports the firmware's ACK line, so an
inverted binding is caught before a recording instead of after it.
"""

from __future__ import annotations

import queue
import time
from unittest.mock import MagicMock

import pytest

from zebtrack.io.arduino_manager import ArduinoManager

# The reference sketch's replies, keyed by token.
SKETCH_ACKS = {
    1: b"Red LED 1 ON\n",
    2: b"Red LED 1 OFF\n",
    3: b"Blue LED ON\n",
    4: b"Blue LED OFF\n",
    5: b"Green LED ON\n",
    6: b"Green LED OFF\n",
    7: b"Red LED 2 ON\n",
    8: b"Red LED 2 OFF\n",
}


@pytest.fixture
def mock_controller():
    controller = MagicMock()
    controller.on_arduino_status_change = MagicMock()
    controller.log_arduino_event = MagicMock()
    controller.on_arduino_command_sent = MagicMock()
    controller.on_arduino_event = MagicMock()
    return controller


@pytest.fixture
def echo_arduino():
    """Fake Arduino that answers each token like the reference sketch does."""
    arduino = MagicMock()
    arduino.connect = MagicMock(return_value=True)
    arduino.close = MagicMock()
    arduino.ser = MagicMock()
    arduino.ser.is_open = True

    replies: queue.Queue[bytes] = queue.Queue()

    def send_command_async(token):
        replies.put(SKETCH_ACKS.get(int(token), b"Unknown command\n"))
        return True

    def readline():
        try:
            return replies.get(timeout=0.05)
        except queue.Empty:
            return b""

    arduino.send_command_async = MagicMock(side_effect=send_command_async)
    arduino.send_command = MagicMock(return_value=True)
    arduino.ser.readline = MagicMock(side_effect=readline)
    return arduino


@pytest.fixture
def manager(mock_controller, echo_arduino):
    mgr = ArduinoManager(mock_controller, arduino_factory=lambda port, baud: echo_arduino)
    # The writer throttles sends to protect the firmware; a probe of 8 tokens
    # would otherwise take 1.6s of pure sleeping in the test.
    mgr._min_send_interval_s = 0.0
    mgr.connect("COM_TEST", 9600, ack="none")
    yield mgr
    mgr.shutdown()


def test_probe_returns_ack_per_token_in_order(manager):
    results = manager.probe_tokens([1, 2, 3, 4], timeout_s=5.0)

    assert [token for token, _ack in results] == [1, 2, 3, 4]
    assert [ack for _token, ack in results] == [
        "Red LED 1 ON",
        "Red LED 1 OFF",
        "Blue LED ON",
        "Blue LED OFF",
    ]


def test_probe_surfaces_the_inverted_layout(manager):
    """The 2026-08-04 bindings: Z1=1/5, Z2=2/6 — 'enter' answers OFF for Z2."""
    results = manager.probe_tokens([1, 5, 2, 6], timeout_s=5.0)
    acks = {token: ack for token, ack in results}

    assert acks[1] == "Red LED 1 ON"
    assert acks[5] == "Green LED ON"  # a ROI *exit* would turn something ON
    assert acks[2] == "Red LED 1 OFF"  # a ROI *enter* would turn something OFF


def test_probe_handles_duplicate_tokens(manager):
    results = manager.probe_tokens([3, 3], timeout_s=5.0)
    assert results == [(3, "Blue LED ON"), (3, "Blue LED ON")]


def test_probe_empty_list_is_a_noop(manager):
    assert manager.probe_tokens([], timeout_s=5.0) == []


def test_probe_clears_the_sink_afterwards(manager):
    """A probe must not leave the latency sink installed for the next session."""
    manager.probe_tokens([1], timeout_s=5.0)
    assert manager._latency_sink is None


def test_probe_requires_connection(mock_controller):
    mgr = ArduinoManager(mock_controller)
    with pytest.raises(RuntimeError, match="não está conectado"):
        mgr.probe_tokens([1])


def test_probe_refuses_while_a_session_owns_the_sink(manager):
    """Probing hijacks the latency sink, so it must not run mid-recording."""
    manager.set_latency_sink(lambda *args: None)
    try:
        with pytest.raises(RuntimeError, match="sessão ao vivo"):
            manager.probe_tokens([1])
    finally:
        manager.set_latency_sink(None)


def test_probe_reports_none_for_a_silent_firmware(mock_controller):
    """A sketch that never answers yields None rather than hanging forever."""
    mute = MagicMock()
    mute.connect = MagicMock(return_value=True)
    mute.close = MagicMock()
    mute.ser = MagicMock()
    mute.ser.is_open = True
    mute.send_command_async = MagicMock(return_value=True)
    mute.send_command = MagicMock(return_value=True)

    def slow_empty():
        time.sleep(0.01)
        return b""

    mute.ser.readline = MagicMock(side_effect=slow_empty)

    mgr = ArduinoManager(mock_controller, arduino_factory=lambda port, baud: mute)
    mgr._min_send_interval_s = 0.0
    mgr.connect("COM_TEST", 9600, ack="none")
    try:
        results = mgr.probe_tokens([1, 2], timeout_s=0.3)
    finally:
        mgr.shutdown()

    assert results == [(1, None), (2, None)]
