import logging
import time
from types import TracebackType
from typing import Optional, Type

import serial

from zebtrack.settings import settings


class Arduino:
    """
    Manages serial communication with an Arduino device.

    This class handles connecting, sending commands, and receiving acknowledgments.
    It is designed to be used as a context manager to ensure that the serial
    connection is always closed properly.

    The expected communication protocol is as follows:
    1. On connection, the Arduino sends a ready message: "Arduino is ready.\\n".
    2. The host sends a command as an integer followed by a newline (e.g., "1\\n").
    3. The Arduino processes the command and responds with "OK\\n" to acknowledge.
    """

    def __init__(self, port: str, baud_rate: int):
        """
        Initializes the Arduino controller.
        Args:
            port (str): The serial port the Arduino is connected to.
            baud_rate (int): The baud rate for the serial communication.
        """
        self.port = port
        self.baud_rate = baud_rate
        self.ser: Optional[serial.Serial] = None
        logging.info("Arduino module initialized in offline mode.")

    def connect(self) -> bool:
        """
        Attempts to establish a serial connection with the Arduino. It waits for a
        "ready" signal from the Arduino after opening the serial port.
        Returns True on success, False on failure.
        """
        if self.ser and self.ser.is_open:
            logging.info("Already connected to Arduino.")
            return True
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
            # The Arduino is expected to send a "ready" signal upon startup.
            # This is more robust than a fixed sleep().
            ready_signal = self.ser.readline().decode("utf-8").strip()
            if ready_signal == "Arduino is ready.":
                logging.info(f"Successfully connected to Arduino on port {self.port}")
                return True
            else:
                logging.warning(f"Arduino on port {self.port} did not send ready signal. "
                                f"Received: '{ready_signal}'")
                self.ser.close()
                self.ser = None
                return False
        except (serial.SerialException, OSError) as e:
            logging.warning(f"Could not connect to Arduino on port {self.port}. {e}")
            logging.warning("Running in offline mode. No commands will be sent to Arduino.")
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
        Args:
            box_number (int): The command number to send.
        Returns:
            bool: True if the command was sent and acknowledged, False otherwise.
        """
        try:
            # Ensure box_number is an integer
            command_num = int(box_number)
        except (ValueError, TypeError):
            logging.error(f"Invalid command: '{box_number}' is not a valid integer.")
            return False

        if self.ser and self.ser.is_open:
            command = f"{command_num}\n"
            try:
                self.ser.write(command.encode("utf-8"))
                logging.info(f"Sent command to Arduino: {command.strip()}")

                # Wait for acknowledgment
                response = self.ser.readline().decode("utf-8").strip()
                if response == "OK":
                    logging.info("Arduino acknowledged command.")
                    return True
                else:
                    logging.warning(
                        f"Arduino acknowledgment failed. Expected 'OK', got '{response}'"
                    )
                    return False
            except serial.SerialException as e:
                logging.error(f"Error during serial communication: {e}")
                return False
        else:
            logging.debug(f"Offline mode: Command '{command_num}' not sent.")
            return False

    def close(self) -> None:
        """
        Closes the serial connection and clears the serial object.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Arduino connection closed.")
        self.ser = None


def main():
    """Main function to run a test of the Arduino module."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("Testing Arduino communication...")

    if not settings:
        print("Settings could not be loaded. Aborting test.")
        return

    # Initialize and use Arduino with a context manager
    try:
        with Arduino(port=settings.arduino.port, baud_rate=settings.arduino.baud_rate) as arduino:
            print(f"Successfully connected to Arduino on {arduino.port}.")

            # Test sending a sequence of commands
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
