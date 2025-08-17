import time
from types import TracebackType
from typing import Optional, Type

import serial
import structlog

from zebtrack.settings import settings

log = structlog.get_logger()


class Arduino:
    """
    Manages serial communication with an Arduino device.
    """

    def __init__(self, port: str, baud_rate: int):
        """
        Initializes the Arduino controller.
        """
        self.port = port
        self.baud_rate = baud_rate
        self.ser: Optional[serial.Serial] = None
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
            if ready_signal == "Arduino is ready.":
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
            log.warning(
                "arduino.connect.failed", port=self.port, exc_info=e
            )
            self.ser = None
            return False

    def __enter__(self) -> "Arduino":
        """Enter the runtime context related to this object."""
        if not self.connect():
            raise RuntimeError(f"Failed to connect to Arduino on port {self.port}")
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Exit the runtime context and close the connection."""
        self.close()

    def send_command(self, box_number: int) -> bool:
        """
        Sends a command to the Arduino and waits for an acknowledgment.
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

    def close(self) -> None:
        """
        Closes the serial connection.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("arduino.connection.closed")
        self.ser = None


def main():
    """Main function to run a test of the Arduino module."""
    # This is a test function, using print is fine here.
    print("Testing Arduino communication...")

    if not settings:
        print("Settings could not be loaded. Aborting test.")
        return

    try:
        with Arduino(
            port=settings.arduino.port, baud_rate=settings.arduino.baud_rate
        ) as arduino:
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
