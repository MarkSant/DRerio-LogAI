"""
Unit tests for ArduinoFacade.

Tests the facade pattern for Arduino operations, ensuring proper
coordination with ArduinoManager and StateManager.
"""

from unittest.mock import Mock

import pytest

from zebtrack.core.arduino_facade import ArduinoFacade


@pytest.fixture
def mock_arduino_manager():
    """Create mock ArduinoManager."""
    manager = Mock()
    manager.list_available_ports = Mock(return_value=[])
    manager.connect = Mock(return_value=True)
    manager.disconnect = Mock()
    manager.send_command = Mock()
    manager.is_connected = Mock(return_value=False)
    return manager


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    sm = Mock()
    recording_state = Mock()
    recording_state.arduino_connected = False
    recording_state.arduino_port = None
    sm.get_recording_state = Mock(return_value=recording_state)
    sm.update_recording_state = Mock()
    return sm


@pytest.fixture
def arduino_facade(mock_arduino_manager, mock_state_manager):
    """Create ArduinoFacade with mocked dependencies."""
    return ArduinoFacade(
        arduino_manager=mock_arduino_manager,
        state_manager=mock_state_manager,
    )


class TestArduinoFacadeInitialization:
    """Test suite for ArduinoFacade initialization."""

    def test_init_with_all_dependencies(self, mock_arduino_manager, mock_state_manager):
        """Test initialization with all dependencies."""
        facade = ArduinoFacade(
            arduino_manager=mock_arduino_manager,
            state_manager=mock_state_manager,
        )

        assert facade.arduino == mock_arduino_manager
        assert facade.state_manager == mock_state_manager


class TestArduinoFacadeScanPorts:
    """Test suite for scan_ports method."""

    def test_scan_ports_success(self, arduino_facade, mock_arduino_manager):
        """Test successful port scanning."""
        expected_ports = ["COM3", "COM4", "/dev/ttyUSB0"]
        mock_arduino_manager.list_available_ports.return_value = expected_ports

        result = arduino_facade.scan_ports()

        assert result == expected_ports
        mock_arduino_manager.list_available_ports.assert_called_once()

    def test_scan_ports_no_ports_found(self, arduino_facade, mock_arduino_manager):
        """Test scan_ports when no ports are available."""
        mock_arduino_manager.list_available_ports.return_value = []

        result = arduino_facade.scan_ports()

        assert result == []

    def test_scan_ports_handles_exception(self, arduino_facade, mock_arduino_manager):
        """Test scan_ports handles exceptions gracefully."""
        mock_arduino_manager.list_available_ports.side_effect = RuntimeError("Test error")

        result = arduino_facade.scan_ports()

        assert result == []


class TestArduinoFacadeConnect:
    """Test suite for connect method."""

    def test_connect_success(self, arduino_facade, mock_arduino_manager, mock_state_manager):
        """Test successful connection to Arduino."""
        port = "COM3"
        baudrate = 9600
        mock_arduino_manager.connect.return_value = True

        result = arduino_facade.connect(port, baudrate)

        assert result is True
        mock_arduino_manager.connect.assert_called_once_with(port, baudrate)
        mock_state_manager.update_recording_state.assert_called_once()

    def test_connect_updates_state(self, arduino_facade, mock_state_manager):
        """Test that connect updates StateManager on success."""
        port = "COM3"

        arduino_facade.connect(port)

        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["arduino_connected"] is True
        assert call_kwargs["arduino_port"] == port

    def test_connect_failure(self, arduino_facade, mock_arduino_manager, mock_state_manager):
        """Test connect when connection fails."""
        port = "COM3"
        mock_arduino_manager.connect.return_value = False

        result = arduino_facade.connect(port)

        assert result is False
        mock_state_manager.update_recording_state.assert_not_called()

    def test_connect_handles_exception(
        self, arduino_facade, mock_arduino_manager, mock_state_manager
    ):
        """Test connect handles exceptions gracefully."""
        port = "COM3"
        mock_arduino_manager.connect.side_effect = RuntimeError("Test error")

        result = arduino_facade.connect(port)

        assert result is False
        mock_state_manager.update_recording_state.assert_not_called()

    def test_connect_with_custom_baudrate(self, arduino_facade, mock_arduino_manager):
        """Test connect with custom baudrate."""
        port = "COM3"
        baudrate = 115200
        mock_arduino_manager.connect.return_value = True

        result = arduino_facade.connect(port, baudrate)

        assert result is True
        mock_arduino_manager.connect.assert_called_once_with(port, baudrate)


class TestArduinoFacadeDisconnect:
    """Test suite for disconnect method."""

    def test_disconnect_success(self, arduino_facade, mock_arduino_manager, mock_state_manager):
        """Test successful disconnection."""
        result = arduino_facade.disconnect()

        assert result is True
        mock_arduino_manager.disconnect.assert_called_once()
        mock_state_manager.update_recording_state.assert_called_once()

    def test_disconnect_updates_state(self, arduino_facade, mock_state_manager):
        """Test that disconnect updates StateManager."""
        arduino_facade.disconnect()

        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["arduino_connected"] is False
        assert call_kwargs["arduino_port"] is None

    def test_disconnect_handles_exception(
        self, arduino_facade, mock_arduino_manager, mock_state_manager
    ):
        """Test disconnect handles exceptions gracefully."""
        mock_arduino_manager.disconnect.side_effect = RuntimeError("Test error")

        result = arduino_facade.disconnect()

        assert result is False


class TestArduinoFacadeSendCommand:
    """Test suite for send_command method."""

    def test_send_command_success(self, arduino_facade, mock_arduino_manager):
        """Test successful command sending."""
        command = "LED_ON"
        mock_arduino_manager.is_connected.return_value = True

        result = arduino_facade.send_command(command)

        assert result is True
        mock_arduino_manager.send_command.assert_called_once_with(command)

    def test_send_command_not_connected(self, arduino_facade, mock_arduino_manager):
        """Test send_command when not connected."""
        command = "LED_ON"
        mock_arduino_manager.is_connected.return_value = False

        result = arduino_facade.send_command(command)

        assert result is False
        mock_arduino_manager.send_command.assert_not_called()

    def test_send_command_handles_exception(self, arduino_facade, mock_arduino_manager):
        """Test send_command handles exceptions gracefully."""
        command = "LED_ON"
        mock_arduino_manager.is_connected.return_value = True
        mock_arduino_manager.send_command.side_effect = RuntimeError("Test error")

        result = arduino_facade.send_command(command)

        assert result is False


class TestArduinoFacadeIsConnected:
    """Test suite for is_connected method."""

    def test_is_connected_true(self, arduino_facade, mock_arduino_manager):
        """Test is_connected returns True when connected."""
        mock_arduino_manager.is_connected.return_value = True

        assert arduino_facade.is_connected() is True

    def test_is_connected_false(self, arduino_facade, mock_arduino_manager):
        """Test is_connected returns False when not connected."""
        mock_arduino_manager.is_connected.return_value = False

        assert arduino_facade.is_connected() is False


class TestArduinoFacadeGetters:
    """Test suite for getter methods."""

    def test_get_connected_port_when_connected(self, arduino_facade, mock_state_manager):
        """Test get_connected_port when Arduino is connected."""
        expected_port = "COM3"
        recording_state = Mock()
        recording_state.arduino_port = expected_port
        mock_state_manager.get_recording_state.return_value = recording_state

        result = arduino_facade.get_connected_port()

        assert result == expected_port

    def test_get_connected_port_when_not_connected(self, arduino_facade, mock_state_manager):
        """Test get_connected_port when Arduino is not connected."""
        recording_state = Mock()
        recording_state.arduino_port = None
        mock_state_manager.get_recording_state.return_value = recording_state

        result = arduino_facade.get_connected_port()

        assert result is None

    def test_get_status_connected(self, arduino_facade, mock_state_manager):
        """Test get_status when connected."""
        expected_port = "COM3"
        recording_state = Mock()
        recording_state.arduino_connected = True
        recording_state.arduino_port = expected_port
        mock_state_manager.get_recording_state.return_value = recording_state

        status = arduino_facade.get_status()

        assert status["connected"] is True
        assert status["port"] == expected_port

    def test_get_status_disconnected(self, arduino_facade, mock_state_manager):
        """Test get_status when not connected."""
        recording_state = Mock()
        recording_state.arduino_connected = False
        recording_state.arduino_port = None
        mock_state_manager.get_recording_state.return_value = recording_state

        status = arduino_facade.get_status()

        assert status["connected"] is False
        assert status["port"] is None
