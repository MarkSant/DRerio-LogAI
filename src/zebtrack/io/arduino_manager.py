from __future__ import annotations

import threading
import time
from collections.abc import Callable

import structlog

from zebtrack.io.arduino import Arduino

try:  # pragma: no cover - serial may not be available during unit tests
    from serial import SerialException  # type: ignore
except Exception:  # pragma: no cover - fallback when pyserial is missing

    class SerialError(Exception):
        """Fallback SerialError when pyserial is not installed."""

        pass

    # Backwards-compatible alias for callers expecting SerialException
    SerialException = SerialError


log = structlog.get_logger()


class ArduinoManager:
    """High-level Arduino coordinator handling connection, commands and events."""

    def __init__(
        self,
        controller,
        arduino_factory: Callable[[str, int], Arduino] = Arduino,
    ) -> None:
        self.controller = controller
        self._arduino_factory = arduino_factory
        self.arduino: Arduino | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._port: str | None = None
        self._baud_rate: int | None = None
        self._last_command: int | None = None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def connect(self, port: str, baud_rate: int) -> bool:
        """Connects to Arduino and starts reader loop."""
        with self._lock:
            if self.is_connected() and self._port == port:
                log.debug("arduino_manager.connect.already_connected", port=port)
                return True

            self._shutdown_reader_locked()

            try:
                candidate = self._arduino_factory(port, baud_rate)
            except Exception:  # pragma: no cover - constructor errors are rare
                log.error(
                    "arduino_manager.connect.init_failed",
                    port=port,
                    baud_rate=baud_rate,
                    exc_info=True,
                )
                self._notify_log(f"Falha ao inicializar o Arduino na porta {port}.")
                return False

            try:
                if not candidate.connect():
                    log.warning(
                        "arduino_manager.connect.handshake_failed",
                        port=port,
                    )
                    candidate.close()
                    self._notify_status(False, port)
                    self._notify_log(f"Não foi possível conectar ao Arduino na porta {port}.")
                    return False
            except Exception:
                log.error(
                    "arduino_manager.connect.failed",
                    port=port,
                    baud_rate=baud_rate,
                    exc_info=True,
                )
                candidate.close()
                self._notify_status(False, port)
                self._notify_log(f"Erro ao conectar ao Arduino na porta {port}.")
                return False

            self.arduino = candidate
            self._port = port
            self._baud_rate = baud_rate
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="ArduinoReader",
                daemon=True,
            )
            self._reader_thread.start()

        log.info("arduino_manager.connect.success", port=port, baud_rate=baud_rate)
        self._notify_status(True, port)
        self._notify_log(f"Arduino conectado na porta {port}.")
        return True

    def disconnect(self) -> None:
        """Disconnects from Arduino and stops reader loop."""
        with self._lock:
            self._shutdown_reader_locked()
            self._port = None
            self._baud_rate = None

        self._notify_status(False, None)
        self._notify_log("Arduino desconectado.")

    def is_connected(self) -> bool:
        """Checks whether the Arduino is connected and serial port is open."""
        if not self.arduino:
            return False
        serial_conn = getattr(self.arduino, "ser", None)
        return bool(serial_conn and getattr(serial_conn, "is_open", False))

    def current_port(self) -> str | None:
        """Returns the serial port in use, if any."""
        return self._port

    def send_command(self, command: int, *, source: str = "auto") -> bool:
        """Sends a command to Arduino and reports outcome to controller."""
        if not self.is_connected():
            self._notify_log("Não foi possível enviar comando: Arduino desconectado.")
            self._notify_command(command, success=False, source=source)
            return False

        success = False
        try:
            assert self.arduino is not None
            success = bool(self.arduino.send_command(command))
        except Exception:
            log.error(
                "arduino_manager.command.error",
                command=command,
                exc_info=True,
            )
            success = False

        if success:
            self._last_command = command
            self._notify_log(f"Comando {command} enviado ao Arduino.")
        else:
            self._notify_log(f"Falha ao enviar comando {command} ao Arduino.")

        self._notify_command(command, success=success, source=source)
        return success

    def last_command(self) -> int | None:
        """Returns the last successful command sent."""
        return self._last_command

    def shutdown(self) -> None:
        """Stops reader thread and closes Arduino connection."""
        self.disconnect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _shutdown_reader_locked(self) -> None:
        self._stop_event.set()
        thread = self._reader_thread
        self._reader_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        if self.arduino:
            try:
                self.arduino.close()
            except Exception:  # pragma: no cover - best effort close
                log.warning("arduino_manager.disconnect.close_error", exc_info=True)
            self.arduino = None
        self._stop_event.clear()

    def _reader_loop(self) -> None:
        """Continuously reads from serial port and dispatches events."""
        log.debug("arduino_manager.reader.start", port=self._port)
        while not self._stop_event.is_set():
            if not self.is_connected():
                time.sleep(0.25)
                continue

            assert self.arduino is not None
            serial_conn = getattr(self.arduino, "ser", None)
            if not serial_conn:
                time.sleep(0.5)
                continue

            try:
                raw_line = serial_conn.readline()
            except SerialException:
                log.warning("arduino_manager.reader.serial_exception", exc_info=True)
                self._notify_log("Conexão serial com Arduino perdida.")
                self.disconnect()
                break
            except Exception:
                log.warning("arduino_manager.reader.generic_error", exc_info=True)
                time.sleep(0.5)
                continue

            if not raw_line:
                continue

            try:
                decoded = raw_line.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue

            if not decoded:
                continue

            if self._is_int(decoded):
                event_code = int(decoded)
                self._dispatch_event(event_code)
            else:
                self._notify_log(f"Arduino: {decoded}")

        log.debug("arduino_manager.reader.stop", port=self._port)

    def _dispatch_event(self, event_code: int) -> None:
        log.info("arduino_manager.event", code=event_code)
        try:
            if hasattr(self.controller, "on_arduino_event"):
                self.controller.on_arduino_event(event_code)
        except Exception:  # pragma: no cover - controller should handle safely
            log.error("arduino_manager.event.dispatch_failed", code=event_code, exc_info=True)

    def _notify_status(self, connected: bool, port: str | None) -> None:
        try:
            if hasattr(self.controller, "on_arduino_status_change"):
                self.controller.on_arduino_status_change(connected, port)
        except Exception:  # pragma: no cover - UI callbacks must not break flow
            log.warning("arduino_manager.status.notify_failed", exc_info=True)

    def _notify_log(self, message: str) -> None:
        try:
            if hasattr(self.controller, "log_arduino_event"):
                self.controller.log_arduino_event(message)
        except Exception:  # pragma: no cover
            log.warning("arduino_manager.log.notify_failed", exc_info=True)

    def _notify_command(self, command: int, *, success: bool, source: str) -> None:
        try:
            if hasattr(self.controller, "on_arduino_command_sent"):
                self.controller.on_arduino_command_sent(command, success, source)
        except Exception:  # pragma: no cover
            log.warning("arduino_manager.command.notify_failed", exc_info=True)

    @staticmethod
    def _is_int(value: str) -> bool:
        if not value:
            return False
        if value.startswith("-"):
            return value[1:].isdigit()
        return value.isdigit()
