import serial
import time
import config

class Arduino:
    def __init__(self):
        """Initializes the Arduino controller in an offline state."""
        self.ser = None
        logging.info("Arduino module initialized in offline mode.")

    def connect(self):
        """
        Attempts to establish a serial connection with the Arduino.
        Returns True on success, False on failure.
        """
        if self.ser and self.ser.is_open:
            logging.info("Already connected to Arduino.")
            return True
        try:
            self.ser = serial.Serial(config.ARDUINO_PORT, config.BAUD_RATE, timeout=1)
            time.sleep(2)  # Wait for the connection to establish
            logging.info(f"Successfully connected to Arduino on port {config.ARDUINO_PORT}")
            return True
        except serial.SerialException as e:
            logging.warning(f"Could not connect to Arduino on port {config.ARDUINO_PORT}. {e}")
            logging.warning("Running in offline mode. No commands will be sent to Arduino.")
            self.ser = None
            return False

    def send_command(self, box_number):
        """
        Sends a command to the Arduino.
        """
        if self.ser and self.ser.is_open:
            command = f"{box_number}\n"
            try:
                self.ser.write(command.encode('utf-8'))
                logging.info(f"Sent command to Arduino: {command.strip()}")
            except serial.SerialException as e:
                logging.error(f"Error writing to serial port: {e}")
        else:
            logging.debug(f"Offline mode: Command '{box_number}' not sent.")

    def close(self):
        """
        Closes the serial connection.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Arduino connection closed.")

if __name__ == '__main__':
    # Example usage for testing the Arduino module
    print("Testing Arduino communication...")
    arduino = Arduino()

    if arduino.ser:
        try:
            # Test sending a sequence of commands
            print("\nSending test commands...")
            for i in range(1, 9):
                arduino.send_command(i)
                time.sleep(1)
            print("\nTest commands finished.")

        except KeyboardInterrupt:
            print("\nTest interrupted by user.")

        finally:
            arduino.close()
    else:
        print("\nCould not run test, Arduino not connected.")

    print("\nSimulating offline mode:")
    # To test offline mode, we can't just re-init, so this part is for demonstration
    offline_arduino = Arduino()
    offline_arduino.ser = None # Manually simulate failed connection
    offline_arduino.send_command(1)
    offline_arduino.close()

    print("\nTest script finished.")
