"""Comprehensive tests for io/arduino_manager.py."""

import time
from unittest.mock import MagicMock

import pytest

from tests.utils.wait_helpers import wait_for_condition
from zebtrack.io.arduino_manager import ArduinoManager


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    controller = MagicMock()
    controller.on_arduino_status_change = MagicMock()
    controller.log_arduino_event = MagicMock()
    controller.on_arduino_command_sent = MagicMock()
    controller.on_arduino_event = MagicMock()
    return controller


@pytest.fixture
def mock_arduino():
    """Create a mock Arduino instance."""
    arduino = MagicMock()
    arduino.connect = MagicMock(return_value=True)
    arduino.close = MagicMock()
    arduino.send_command = MagicMock(return_value=True)
    arduino.ser = MagicMock()
    arduino.ser.is_open = True

    def delayed_readline():
        time.sleep(0.01)  # intentional delay for mock readline
        return b""

    arduino.ser.readline = MagicMock(side_effect=delayed_readline)
    return arduino


@pytest.fixture
def arduino_factory(mock_arduino):
    """Create a factory that returns mock Arduino."""

    def factory(port: str, baud_rate: int):
        return mock_arduino

    return factory


def test_arduino_manager_init(mock_controller):
    """Test ArduinoManager initialization."""
    manager = ArduinoManager(mock_controller)

    assert manager.controller == mock_controller
    assert manager.arduino is None
    assert manager._reader_thread is None
    assert manager._port is None
    assert manager._baud_rate is None
    assert manager._last_command is None


def test_arduino_manager_connect_success(mock_controller, arduino_factory, mock_arduino):
    """Test successful Arduino connection."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    result = manager.connect("COM3", 9600)

    assert result is True
    assert manager.arduino == mock_arduino
    assert manager._port == "COM3"
    assert manager._baud_rate == 9600
    assert manager._reader_thread is not None
    assert manager._reader_thread.is_alive()

    mock_arduino.connect.assert_called_once()
    mock_controller.on_arduino_status_change.assert_called_with(True, "COM3")
    mock_controller.log_arduino_event.assert_called_with("Arduino connected on port COM3.")

    # Cleanup
    manager.disconnect()


def test_arduino_manager_connect_already_connected(mock_controller, arduino_factory, mock_arduino):
    """Test connecting when already connected to the same port."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    # First connection
    result1 = manager.connect("COM3", 9600)
    assert result1 is True

    # Reset mocks
    mock_arduino.connect.reset_mock()
    mock_controller.on_arduino_status_change.reset_mock()

    # Second connection to same port
    result2 = manager.connect("COM3", 9600)
    assert result2 is True

    # Should not reconnect
    mock_arduino.connect.assert_not_called()

    # Cleanup
    manager.disconnect()


def test_arduino_manager_connect_handshake_failed(mock_controller, arduino_factory, mock_arduino):
    """Test connection when handshake fails."""
    mock_arduino.connect.return_value = False

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    result = manager.connect("COM3", 9600)

    assert result is False
    assert manager.arduino is None

    mock_arduino.close.assert_called_once()
    mock_controller.on_arduino_status_change.assert_called_with(False, "COM3")
    mock_controller.log_arduino_event.assert_called_with(
        "Could not connect to the Arduino on port COM3."
    )


def test_arduino_manager_connect_exception_during_handshake(
    mock_controller, arduino_factory, mock_arduino
):
    """Test connection when exception occurs during handshake."""
    mock_arduino.connect.side_effect = Exception("Connection error")

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    result = manager.connect("COM3", 9600)

    assert result is False
    assert manager.arduino is None

    mock_arduino.close.assert_called_once()
    mock_controller.on_arduino_status_change.assert_called_with(False, "COM3")


def test_arduino_manager_disconnect(mock_controller, arduino_factory, mock_arduino):
    """Test Arduino disconnection."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    # Connect first
    manager.connect("COM3", 9600)
    assert manager.is_connected() is True

    # Disconnect
    manager.disconnect()

    assert manager.arduino is None
    assert manager._port is None
    assert manager._baud_rate is None
    assert manager._reader_thread is None

    mock_arduino.close.assert_called()
    mock_controller.on_arduino_status_change.assert_called_with(False, None)
    mock_controller.log_arduino_event.assert_called_with("Arduino disconnected.")


def test_arduino_manager_is_connected_when_connected(
    mock_controller, arduino_factory, mock_arduino
):
    """Test is_connected returns True when connected."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    manager.connect("COM3", 9600)
    assert manager.is_connected() is True

    manager.disconnect()


def test_arduino_manager_is_connected_when_not_connected(mock_controller):
    """Test is_connected returns False when not connected."""
    manager = ArduinoManager(mock_controller)
    assert manager.is_connected() is False


def test_arduino_manager_is_connected_when_port_closed(
    mock_controller, arduino_factory, mock_arduino
):
    """Test is_connected returns False when serial port is closed."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    manager.connect("COM3", 9600)
    mock_arduino.ser.is_open = False

    assert manager.is_connected() is False

    manager.disconnect()


def test_arduino_manager_current_port(mock_controller, arduino_factory):
    """Test current_port returns correct port."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    assert manager.current_port() is None

    manager.connect("COM3", 9600)
    assert manager.current_port() == "COM3"

    manager.disconnect()
    assert manager.current_port() is None


def test_arduino_manager_send_command_success(mock_controller, arduino_factory, mock_arduino):
    """Test successful command sending."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    result = manager.send_command(42)

    assert result is True
    assert manager.last_command() == 42

    mock_arduino.send_command.assert_called_once_with(42)
    mock_controller.log_arduino_event.assert_any_call("Command 42 sent to the Arduino.")
    mock_controller.on_arduino_command_sent.assert_called_with(42, True, "auto")

    manager.disconnect()


def test_arduino_manager_send_command_custom_source(mock_controller, arduino_factory, mock_arduino):
    """Test command sending with custom source."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    manager.send_command(42, source="manual")

    mock_controller.on_arduino_command_sent.assert_called_with(42, True, "manual")

    manager.disconnect()


def test_arduino_manager_send_command_not_connected(mock_controller):
    """Test command sending when not connected."""
    manager = ArduinoManager(mock_controller)

    result = manager.send_command(42)

    assert result is False
    assert manager.last_command() is None

    mock_controller.log_arduino_event.assert_called_with(
        "Could not send command: Arduino disconnected."
    )
    mock_controller.on_arduino_command_sent.assert_called_with(42, False, "auto")


def test_arduino_manager_send_command_exception(mock_controller, arduino_factory, mock_arduino):
    """Test command sending when exception occurs."""
    mock_arduino.send_command.side_effect = Exception("Send error")

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    result = manager.send_command(42)

    assert result is False

    mock_controller.log_arduino_event.assert_any_call("Failed to send command 42 to the Arduino.")
    mock_controller.on_arduino_command_sent.assert_called_with(42, False, "auto")

    manager.disconnect()


def test_send_command_ack_none_uses_async(mock_controller, arduino_factory, mock_arduino):
    """With ack='none', send_command is fire-and-forget (no blocking ACK read)."""
    mock_arduino.send_command_async = MagicMock(return_value=True)

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600, ack="none")

    result = manager.send_command(42)

    assert result is True
    assert manager.last_command() == 42
    mock_arduino.send_command_async.assert_called_once_with(42)
    mock_arduino.send_command.assert_not_called()

    manager.disconnect()


def test_send_command_ack_ok_uses_blocking(mock_controller, arduino_factory, mock_arduino):
    """The default ack policy keeps the legacy blocking send_command path."""
    mock_arduino.send_command_async = MagicMock(return_value=True)

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)  # default ack='ok'

    manager.send_command(7)

    mock_arduino.send_command.assert_called_once_with(7)
    mock_arduino.send_command_async.assert_not_called()

    manager.disconnect()


def test_arduino_manager_last_command(mock_controller, arduino_factory, mock_arduino):
    """Test last_command tracking."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    assert manager.last_command() is None

    manager.send_command(10)
    assert manager.last_command() == 10

    manager.send_command(20)
    assert manager.last_command() == 20

    manager.disconnect()


def test_arduino_manager_shutdown(mock_controller, arduino_factory, mock_arduino):
    """Test shutdown method."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    manager.shutdown()

    assert manager.arduino is None
    assert manager._port is None


@pytest.mark.slow
def test_arduino_manager_reader_loop_event_dispatch(mock_controller, arduino_factory, mock_arduino):
    """Test reader loop dispatches events."""
    mock_arduino.ser.readline.side_effect = [b"42\n", b""]  # Event code, then empty

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    # Wait for reader thread to actually process (with timeout)
    if manager._reader_thread:
        manager._reader_thread.join(timeout=1.0)

    manager.disconnect()

    # Check if event was dispatched
    mock_controller.on_arduino_event.assert_called()


@pytest.mark.slow
def test_arduino_manager_reader_loop_text_message(mock_controller, arduino_factory, mock_arduino):
    """Test reader loop handles text messages."""
    mock_arduino.ser.readline.side_effect = [b"Hello from Arduino\n", b""]

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    # Wait for reader thread to actually process (with timeout)
    if manager._reader_thread:
        manager._reader_thread.join(timeout=1.0)

    manager.disconnect()

    # Check if text was logged
    mock_controller.log_arduino_event.assert_any_call("Arduino: Hello from Arduino")


def test_arduino_manager_is_int_helper():
    """Test _is_int static method."""
    from zebtrack.io.arduino_manager import ArduinoManager

    assert ArduinoManager._is_int("42") is True
    assert ArduinoManager._is_int("-42") is True
    assert ArduinoManager._is_int("0") is True
    assert ArduinoManager._is_int("123") is True

    assert ArduinoManager._is_int("") is False
    assert ArduinoManager._is_int("abc") is False
    assert ArduinoManager._is_int("12.5") is False
    assert ArduinoManager._is_int("12a") is False
    assert ArduinoManager._is_int("-") is False


def test_arduino_manager_connect_different_port(mock_controller, arduino_factory, mock_arduino):
    """Test connecting to a different port disconnects first."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)

    # Connect to first port
    manager.connect("COM3", 9600)
    assert manager._port == "COM3"

    # Reset mocks
    mock_arduino.close.reset_mock()

    # Connect to different port
    manager.connect("COM4", 9600)
    assert manager._port == "COM4"

    # Should have closed the previous connection
    mock_arduino.close.assert_called()

    manager.disconnect()


def test_arduino_manager_thread_is_daemon(mock_controller, arduino_factory):
    """Test that reader thread is daemon."""
    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    assert manager._reader_thread is not None
    assert manager._reader_thread.daemon is True

    manager.disconnect()


@pytest.mark.slow
def test_arduino_manager_reader_loop_handles_serial_exception(
    mock_controller, arduino_factory, mock_arduino
):
    """Test reader loop handles SerialException."""
    from zebtrack.io.arduino_manager import SerialException

    # First call succeeds, second raises SerialException
    mock_arduino.ser.readline.side_effect = [b"", SerialException("Port closed")]

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    # Wait for reader thread to process the exception (with timeout)
    if manager._reader_thread:
        manager._reader_thread.join(timeout=1.0)

    # Should have logged the disconnection
    # Note: The manager should auto-disconnect on SerialException

    manager.shutdown()


def test_arduino_manager_reader_loop_handles_generic_exception(
    mock_controller, arduino_factory, mock_arduino
):
    """Test reader loop handles generic exceptions."""
    # First call succeeds, second raises exception
    mock_arduino.ser.readline.side_effect = [b"", Exception("Unknown error"), b""]

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    # Give reader thread time to process
    wait_for_condition(
        lambda: manager._reader_thread is not None and manager._reader_thread.is_alive(),
        timeout=1.0,
    )

    # Should continue running despite the exception
    manager.disconnect()


def test_arduino_manager_reader_loop_ignores_empty_lines(
    mock_controller, arduino_factory, mock_arduino
):
    """Test reader loop ignores empty lines."""
    mock_arduino.ser.readline.side_effect = [b"", b"\n", b"   \n", b""]

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600)

    # Give reader thread time to process
    wait_for_condition(
        lambda: manager._reader_thread is not None and manager._reader_thread.is_alive(),
        timeout=1.0,
    )

    manager.disconnect()

    # Should not have dispatched any events
    mock_controller.on_arduino_event.assert_not_called()


# --------------------------------------------------------------------------- #
# Writer-thread send throttle (audit 2026-08-02: two zone-transition tokens
# ~255ms apart caused every later ACK to go unmatched for the rest of the
# session, because the firmware was likely still blocked handling the first
# command. ``_throttle_before_send`` enforces a minimum gap between writes.
# --------------------------------------------------------------------------- #


def test_throttle_before_send_skips_wait_on_first_send(mock_controller, monkeypatch):
    """No prior send yet -> nothing to space out, no sleep."""
    manager = ArduinoManager(mock_controller)
    sleep_calls: list[float] = []
    monkeypatch.setattr("zebtrack.io.arduino_manager.time.sleep", sleep_calls.append)

    manager._throttle_before_send()

    assert sleep_calls == []


def test_throttle_before_send_waits_remaining_gap(mock_controller, monkeypatch):
    """Called before the minimum interval elapsed -> sleeps the remainder."""
    manager = ArduinoManager(mock_controller)
    manager._min_send_interval_s = 0.4
    manager._last_send_perf = 100.0
    monkeypatch.setattr("zebtrack.io.arduino_manager.time.perf_counter", lambda: 100.1)
    sleep_calls: list[float] = []
    monkeypatch.setattr("zebtrack.io.arduino_manager.time.sleep", sleep_calls.append)

    manager._throttle_before_send()

    assert sleep_calls == [pytest.approx(0.3, abs=1e-9)]


def test_throttle_before_send_no_wait_when_interval_already_elapsed(mock_controller, monkeypatch):
    """Enough time already passed -> no sleep needed."""
    manager = ArduinoManager(mock_controller)
    manager._min_send_interval_s = 0.4
    manager._last_send_perf = 100.0
    monkeypatch.setattr("zebtrack.io.arduino_manager.time.perf_counter", lambda: 100.5)
    sleep_calls: list[float] = []
    monkeypatch.setattr("zebtrack.io.arduino_manager.time.sleep", sleep_calls.append)

    manager._throttle_before_send()

    assert sleep_calls == []


@pytest.mark.slow
def test_writer_loop_spaces_consecutive_sends_by_min_interval(
    mock_controller, arduino_factory, mock_arduino
):
    """Two tokens enqueued back-to-back must reach the wire >= min interval apart."""
    sent_at: list[float] = []

    def _record(token):
        sent_at.append(time.perf_counter())
        return True

    mock_arduino.send_command_async = MagicMock(side_effect=_record)

    manager = ArduinoManager(mock_controller, arduino_factory=arduino_factory)
    manager.connect("COM3", 9600, ack="none")
    manager._min_send_interval_s = 0.2  # shortened so the test stays fast

    assert manager.enqueue(1)
    assert manager.enqueue(2)

    wait_for_condition(lambda: len(sent_at) >= 2, timeout=2.0)
    manager.disconnect()

    assert len(sent_at) == 2
    gap = sent_at[1] - sent_at[0]
    assert gap >= manager._min_send_interval_s - 0.02  # scheduling tolerance
