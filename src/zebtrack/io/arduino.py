import time
from types import TracebackType
from typing import Any

import serial
import structlog

log = structlog.get_logger()

# Whitelist de comandos permitidos
ALLOWED_ARDUINO_COMMANDS = frozenset({
    "START",
    "STOP",
    "STATUS",
    "TRIGGER",
    "RESET",
    "PING",
})


class ArduinoCommandError(ValueError):
    """Erro quando comando Arduino é inválido."""


class Arduino:
    """
    Manages serial communication with an Arduino device.
    """

    READY_SIGNAL = "Arduino is ready."
    _PROBE_WARMUP_SECONDS = 0.1

    def __init__(self, port: str, baud_rate: int):
        """
        Initializes the Arduino controller.
        """
        self.port = port
        self.baud_rate = baud_rate
        self.ser: serial.Serial | None = None
        log.info("arduino.init", port=self.port, baud_rate=self.baud_rate)

    def connect(self) -> bool:
        """
        Attempts to establish a serial connection with the Arduino.
        """
        if self.ser and self.ser.is_open:
            log.info("arduino.connect.already_connected")
            return True
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
            ready_signal = self.ser.readline().decode("utf-8").strip()
            if ready_signal == self.READY_SIGNAL:
                log.info("arduino.connect.success", port=self.port)
                return True
            else:
                log.warning(
                    "arduino.connect.no_ready_signal",
                    port=self.port,
                    received=ready_signal,
                )
                self.ser.close()
                self.ser = None
                return False
        except (serial.SerialException, OSError) as e:
            log.warning("arduino.connect.failed", port=self.port, exc_info=e)
            self.ser = None
            return False

    def __enter__(self) -> "Arduino":
        """Enter the runtime context related to this object."""
        if not self.connect():
            raise RuntimeError(f"Failed to connect to Arduino on port {self.port}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the runtime context and close the connection."""
        self.close()

    def send_command(self, box_number: int) -> bool:
        """
        Sends a command to the Arduino and waits for an acknowledgment.

        Note: This method sends numeric box numbers for backward compatibility.
        For string-based commands with security validation, use send_string_command().
        """
        try:
            command_num = int(box_number)
        except (ValueError, TypeError):
            log.error("arduino.command.invalid", command=box_number)
            return False

        if self.ser and self.ser.is_open:
            command = f"{command_num}\n"
            try:
                self.ser.write(command.encode("utf-8"))
                log.info("arduino.command.sent", command=command_num)

                response = self.ser.readline().decode("utf-8").strip()
                if response == "OK":
                    log.info("arduino.command.ack", command=command_num)
                    return True
                else:
                    log.warning(
                        "arduino.command.nack",
                        command=command_num,
                        response=response,
                    )
                    return False
            except serial.SerialException as e:
                log.error("arduino.command.send_error", exc_info=e)
                return False
        else:
            log.debug("arduino.command.offline", command=command_num)
            return False

    def send_string_command(self, command: str) -> bool:
        """
        Sends a validated string command to the Arduino.

        Args:
            command: Command string to send (must be in whitelist)

        Returns:
            True if command sent successfully, False otherwise

        Raises:
            ArduinoCommandError: If command not in whitelist
        """
        if not self.ser or not self.ser.is_open:
            log.debug("arduino.command.offline", command=command)
            return False

        # Validar comando contra whitelist
        command_clean = command.strip().upper()

        if command_clean not in ALLOWED_ARDUINO_COMMANDS:
            log.error(
                "arduino.command.rejected",
                command=command,
                allowed=list(ALLOWED_ARDUINO_COMMANDS),
            )
            raise ArduinoCommandError(
                f"Comando inválido: '{command}'. "
                f"Comandos permitidos: {', '.join(sorted(ALLOWED_ARDUINO_COMMANDS))}"
            )

        try:
            command_bytes = f"{command_clean}\n".encode()
            self.ser.write(command_bytes)
            self.ser.flush()
            log.info("arduino.command.sent", command=command_clean)
            return True
        except Exception as e:
            log.error("arduino.command.error", error=str(e), exc_info=True)
            return False

    def close(self) -> None:
        """
        Closes the serial connection.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("arduino.connection.closed")
        self.ser = None

    @classmethod
    def probe_port(
        cls,
        port: str,
        baud_rate: int,
        *,
        timeout: float = 1.5,
        warmup: float | None = None,
    ) -> bool:
        """Attempts to verify that an Arduino responds on the given port."""
        warmup_delay = cls._PROBE_WARMUP_SECONDS if warmup is None else max(warmup, 0)
        try:
            ser = serial.Serial(port, baud_rate, timeout=timeout)
        except (serial.SerialException, OSError):
            log.debug("arduino.probe.open_failed", port=port, exc_info=True)
            return False

        try:
            try:
                ser.reset_input_buffer()
            except Exception:  # pragma: no cover - not all drivers support it
                pass

            if warmup_delay:
                time.sleep(warmup_delay)

            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw_line = ser.readline()
                except Exception:  # pragma: no cover - serial driver quirks
                    break
                if not raw_line:
                    continue
                decoded = raw_line.decode("utf-8", errors="ignore").strip()
                if not decoded:
                    continue
                if decoded == cls.READY_SIGNAL:
                    log.debug("arduino.probe.success", port=port)
                    return True
            log.debug("arduino.probe.timeout", port=port)
            return False
        finally:
            try:
                ser.close()
            except Exception:  # pragma: no cover - best effort close
                pass

    @classmethod
    def scan_available_ports(
        cls, baud_rate: int, *, timeout: float = 1.5
    ) -> tuple[list[Any], list[Any]]:
        """Returns ports that respond to the Arduino handshake and fallbacks."""
        handshake_ports: list[object] = []
        fallback_ports: list[object] = []

        try:
            from serial.tools import list_ports  # type: ignore
        except Exception:  # pragma: no cover - pyserial not installed
            log.warning("arduino.scan.list_ports_unavailable")
            return handshake_ports, fallback_ports

        try:
            ports = list(list_ports.comports())
        except Exception as exc:  # pragma: no cover - driver issues
            log.warning("arduino.scan.list_ports_failed", exc_info=exc)
            return handshake_ports, fallback_ports

        for info in ports:
            device = getattr(info, "device", None)
            if not device:
                fallback_ports.append(info)
                continue
            if cls.probe_port(device, baud_rate, timeout=timeout):
                handshake_ports.append(info)
            else:
                fallback_ports.append(info)

        return handshake_ports, fallback_ports


def main():
    """Main function to run a test of the Arduino module."""
    # This is a test function, using print is fine here.
    print("Testing Arduino communication...")

    # Load settings locally for test
    try:
        from zebtrack.settings import load_settings

        settings = load_settings()
    except Exception as e:
        print(f"Settings could not be loaded: {e}. Aborting test.")
        return

    try:
        with Arduino(port=settings.arduino.port, baud_rate=settings.arduino.baud_rate) as arduino:
            print(f"Successfully connected to Arduino on {arduino.port}.")

            print("\nSending test commands (1 to 8)...")
            all_commands_successful = True
            for i in range(1, 9):
                print(f"Sending command: {i}...")
                if arduino.send_command(i):
                    print(f"Command {i} sent and acknowledged.")
                else:
                    print(f"Command {i} FAILED.")
                    all_commands_successful = False
                time.sleep(0.5)

            if all_commands_successful:
                print("\nAll test commands sent successfully.")
            else:
                print("\nSome test commands failed.")

    except (RuntimeError, serial.SerialException, OSError) as e:
        print(f"\nERROR: {e}")
        print("Running in offline mode. No commands will be sent.")
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    finally:
        print("\nClosing connection (if open).")

    print("\nTest script finished.")


if __name__ == "__main__":
    main()
