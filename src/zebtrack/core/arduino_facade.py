"""
ArduinoFacade: Isola lógica de Arduino do MainViewModel.

Responsabilidades:
- Detecção de portas Arduino
- Conexão/desconexão
- Envio de comandos
- Monitoramento de status
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.arduino_manager import ArduinoManager

log = structlog.get_logger()


class ArduinoFacade:
    """Facade for Arduino operations."""

    def __init__(
        self,
        arduino_manager: ArduinoManager,
        state_manager: StateManager,
    ) -> None:
        """
        Initialize ArduinoFacade.

        Args:
            arduino_manager: ArduinoManager instance
            state_manager: StateManager for connection state
        """
        self.arduino = arduino_manager
        self.state_manager = state_manager

        log.info("arduino_facade.initialized")

    def scan_ports(self) -> list[str]:
        """
        Scan for available Arduino ports.

        Returns:
            List of port names (e.g., ['COM3', 'COM4'])
        """
        try:
            ports = self.arduino.list_available_ports()
            log.info("arduino_facade.scan.found", ports=ports)
            return ports
        # except Exception justified: serial hardware initialization — heterogeneous failures
        except Exception as e:
            log.error("arduino_facade.scan.failed", error=str(e), exc_info=True)
            return []

    def connect(self, port: str, baudrate: int = 9600) -> bool:
        """
        Connect to Arduino on specified port.

        Args:
            port: Serial port name
            baudrate: Baud rate for connection

        Returns:
            True if connected successfully
        """
        try:
            success = self.arduino.connect(port, baudrate)

            if success:
                self.state_manager.update_recording_state(
                    source="arduino_facade.connect",
                    arduino_connected=True,
                    arduino_port=port,
                )
                log.info("arduino_facade.connect.success", port=port)
            else:
                log.warning("arduino_facade.connect.failed", port=port)

            return success

        # except Exception justified: serial command send — hardware I/O boundary
        except Exception as e:
            log.error("arduino_facade.connect.error", error=str(e), exc_info=True)
            return False

    def disconnect(self) -> bool:
        """Disconnect from Arduino."""
        try:
            self.arduino.disconnect()

            self.state_manager.update_recording_state(
                source="arduino_facade.disconnect",
                arduino_connected=False,
                arduino_port=None,
            )

            log.info("arduino_facade.disconnect.success")
            return True

        # except Exception justified: serial port close — cleanup must not propagate
        except Exception as e:
            log.error("arduino_facade.disconnect.error", error=str(e), exc_info=True)
            return False

    def send_command(self, command: str) -> bool:
        """
        Send command to Arduino.

        Args:
            command: Command string

        Returns:
            True if sent successfully
        """
        try:
            if not self.is_connected():
                log.warning("arduino_facade.send.not_connected")
                return False

            self.arduino.send_command(command)
            log.info("arduino_facade.command.sent", command=command)
            return True

        # except Exception justified: serial connection check — hardware-dependent
        except Exception as e:
            log.error("arduino_facade.send.failed", error=str(e), exc_info=True)
            return False

    def is_connected(self) -> bool:
        """Check if Arduino is connected."""
        return self.arduino.is_connected()

    def get_connected_port(self) -> str | None:
        """
        Get the currently connected port.

        Returns:
            Port name if connected, None otherwise
        """
        recording_state = self.state_manager.get_recording_state()
        return recording_state.arduino_port

    def get_status(self) -> dict[str, bool | str | None]:
        """
        Get Arduino connection status.

        Returns:
            Dict with 'connected' and 'port' keys
        """
        recording_state = self.state_manager.get_recording_state()
        return {
            "connected": recording_state.arduino_connected,
            "port": recording_state.arduino_port,
        }
