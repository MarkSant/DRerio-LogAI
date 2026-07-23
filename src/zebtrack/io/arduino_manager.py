from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.io.arduino import Arduino

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

# Callback signature for the closed-loop latency sink:
# ``(context, t_send, t_ack, ack_text)`` — see ``closed_loop_latency``.
LatencySink = Callable[[dict[str, Any], float | None, float | None, str | None], None]

_SerialExceptionBase: type[BaseException]

try:  # pragma: no cover - serial may not be available during unit tests
    from serial import SerialException as _RealSerialException

    _SerialExceptionBase = _RealSerialException
except Exception:  # pragma: no cover - fallback when pyserial is missing

    class _FallbackSerialError(Exception):
        """Fallback SerialException when pyserial is not installed."""

    _SerialExceptionBase = _FallbackSerialError

SerialExceptionType = _SerialExceptionBase
SerialException = _SerialExceptionBase


log = structlog.get_logger()


class ArduinoManager:
    """High-level Arduino coordinator handling connection, commands and events."""

    def __init__(
        self,
        controller: MainViewModel | Any,
        arduino_factory: Callable[[str, int], Arduino] = Arduino,
    ) -> None:
        self.controller = controller
        self._arduino_factory = arduino_factory
        self.arduino: Arduino | None = None
        self._reader_thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        # Queue items are ``(token, context)``: ``context`` is ``None`` for plain
        # fire-and-forget sends and a dict for latency-tracked closed-loop sends.
        self._write_queue: queue.Queue[tuple[int, dict[str, Any] | None]] = queue.Queue()
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._port: str | None = None
        self._baud_rate: int | None = None
        self._last_command: int | None = None
        # Outbound acknowledgement policy for ``send_command``: "ok" waits for an
        # "OK" reply (legacy/blocking), "none" is fire-and-forget. Set per connect.
        self._ack: str = "ok"

        # Closed-loop latency instrumentation (opt-in per live session). The
        # writer stamps ``t_send`` and records a pending entry; the reader stamps
        # ``t_ack`` on the firmware ACK line and matches FIFO (the serial channel
        # is strictly ordered). No-op unless a sink is registered.
        self._latency_lock = threading.Lock()
        self._latency_sink: LatencySink | None = None
        self._pending_acks: deque[tuple[float, dict[str, Any]]] = deque()
        self._max_pending_acks = 512

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def connect(
        self, port: str, baud_rate: int, *, handshake: str = "none", ack: str = "ok"
    ) -> bool:
        """Connects to Arduino and starts reader/writer loops.

        Args:
            port: Serial port to open.
            baud_rate: Serial baud rate.
            handshake: Connection policy forwarded to the ``Arduino`` instance
                ('none' = tolerant, 'ready_line' = strict). Defaults to 'none'.
            ack: Outbound acknowledgement policy for ``send_command``. 'ok'
                (default) keeps the legacy blocking path that waits for an "OK"
                reply; 'none' makes ``send_command`` fire-and-forget (required
                for sketches that do not reply "OK"). Defaults to 'ok' to
                preserve callers that do not opt in.
        """
        with self._lock:
            self._ack = ack
            if self.is_connected() and self._port == port:
                log.debug("arduino_manager.connect.already_connected", port=port)
                return True

            self._shutdown_reader_locked()

            try:
                candidate = self._arduino_factory(port, baud_rate)
                # Apply the handshake policy on the instance so it works whether
                # the factory is the Arduino class or a test double.
                candidate.handshake = handshake
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
            # except Exception justified: Arduino handshake - serial I/O
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
            self._drain_write_queue()
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="ArduinoReader",
                daemon=True,
            )
            self._reader_thread.start()
            self._writer_thread = threading.Thread(
                target=self._writer_loop,
                name="ArduinoWriter",
                daemon=True,
            )
            self._writer_thread.start()

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
        """Checks whether the Arduino is connected and serial port is open.

        Task 1.2: Thread-safe access to arduino instance.
        """
        with self._lock:  # Protect access to self.arduino from concurrent threads
            if not self.arduino:
                return False
            serial_conn = getattr(self.arduino, "ser", None)
            return bool(serial_conn and getattr(serial_conn, "is_open", False))

    def current_port(self) -> str | None:
        """Return the currently connected port, if any."""
        return self._port

    def list_available_ports(self) -> list[str]:
        """List available serial ports using WizardService.

        Returns:
            List of serial port names
        """
        from zebtrack.core.services.wizard_service import WizardService

        ports = WizardService.detect_arduino_ports(use_cache=True)
        return [port.get("device", "") for port in ports if port.get("device")]

    def send_command(self, command: int | str, *, source: str = "auto") -> bool:
        """Sends a command to Arduino and reports outcome to controller."""
        command_value: int
        if isinstance(command, str):
            if not command.isdigit():
                self._notify_log(f"Comando inválido: {command}")
                return False
            command_value = int(command)
        else:
            command_value = command

        with self._lock:
            arduino = self.arduino if self.is_connected() else None
        if arduino is None:
            self._notify_log("Não foi possível enviar comando: Arduino desconectado.")
            self._notify_command(command_value, success=False, source=source)
            return False

        success = False
        try:
            # Honour the ack policy: 'none' is fire-and-forget (no blocking ACK
            # read), required for sketches that never reply "OK".
            if self._ack == "none":
                success = bool(arduino.send_command_async(command_value))
            else:
                success = bool(arduino.send_command(command_value))
        except Exception:  # except Exception justified: serial command send — hardware I/O boundary
            log.error(
                "arduino_manager.command.error",
                command=command,
                exc_info=True,
            )
            success = False

        if success:
            self._last_command = command_value
            self._notify_log(f"Comando {command_value} enviado ao Arduino.")
        else:
            self._notify_log(f"Falha ao enviar comando {command_value} ao Arduino.")

        self._notify_command(command_value, success=success, source=source)
        return success

    def enqueue(self, token: int) -> bool:
        """Queue a numeric token for fire-and-forget delivery to the Arduino.

        Non-blocking: the token is handed to the writer thread, which writes it
        without waiting for an acknowledgment. This is the path used by the
        real-time per-zone command loop so frame processing never stalls on
        serial I/O. Tokens queued while disconnected are dropped.

        Args:
            token: Numeric command to send (e.g. a per-zone enter/exit code).

        Returns:
            True if the token was queued, False if offline or invalid.
        """
        try:
            token_value = int(token)
        except (ValueError, TypeError):
            log.error("arduino_manager.enqueue.invalid", token=token)
            return False

        if not self.is_connected():
            log.debug("arduino_manager.enqueue.offline", token=token_value)
            return False

        self._write_queue.put((token_value, None))
        return True

    def enqueue_tracked(self, token: int, context: dict[str, Any]) -> bool:
        """Queue a token for delivery, carrying latency-tracking ``context``.

        Identical to :meth:`enqueue` but the ``context`` (ROI/edge/token, frame
        capture timestamp, decision timestamp, …) rides along so the writer/
        reader threads can attribute serial ``t_send``/``t_ack`` timestamps back
        to the ROI transition that triggered them. Falls back to a plain,
        untracked send when no latency sink is registered.

        Args:
            token: Numeric command to send.
            context: Opaque per-trigger metadata forwarded to the latency sink.

        Returns:
            True if the token was queued, False if offline or invalid.
        """
        try:
            token_value = int(token)
        except (ValueError, TypeError):
            log.error("arduino_manager.enqueue_tracked.invalid", token=token)
            return False

        if not self.is_connected():
            log.debug("arduino_manager.enqueue_tracked.offline", token=token_value)
            return False

        with self._latency_lock:
            tracked = self._latency_sink is not None
        self._write_queue.put((token_value, context if tracked else None))
        return True

    def set_latency_sink(self, sink: LatencySink | None) -> None:
        """Register (or clear) the closed-loop latency sink for this session.

        Pass ``None`` at session end to stop tracking; any still-pending entries
        are dropped (call :meth:`flush_pending_acks` first to emit them as
        unmatched rows). Registering a sink also clears stale pendings from a
        previous session.
        """
        with self._latency_lock:
            self._latency_sink = sink
            self._pending_acks.clear()

    def flush_pending_acks(self) -> None:
        """Emit every still-unmatched pending trigger with ``t_ack=None``.

        Called at session end so triggers whose ACK never arrived still produce
        a row (with the software-side timings present and the serial metrics
        left empty).
        """
        with self._latency_lock:
            drained = list(self._pending_acks)
            self._pending_acks.clear()
            sink = self._latency_sink
        for t_send, context in drained:
            self._emit_latency(context, t_send, None, None, sink)

    def _emit_latency(
        self,
        context: dict[str, Any],
        t_send: float | None,
        t_ack: float | None,
        ack_text: str | None,
        sink: LatencySink | None = None,
    ) -> None:
        """Invoke the latency sink defensively (never propagate its errors)."""
        if sink is None:
            with self._latency_lock:
                sink = self._latency_sink
        if sink is None:
            return
        try:
            sink(context, t_send, t_ack, ack_text)
        # except Exception justified: the sink is user/session code; a failure
        # must not break serial reading/writing.
        except Exception:
            log.error("arduino_manager.latency.sink_error", exc_info=True)

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
        for attr in ("_reader_thread", "_writer_thread"):
            thread = getattr(self, attr)
            setattr(self, attr, None)
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)
        if self.arduino:
            try:
                self.arduino.close()
            except Exception:  # pragma: no cover - best effort close
                log.warning("arduino_manager.disconnect.close_error", exc_info=True)
            self.arduino = None
        self._drain_write_queue()
        self._stop_event.clear()

    def _drain_write_queue(self) -> None:
        """Discard any pending outbound tokens (e.g. after disconnect)."""
        while True:
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                break
        with self._latency_lock:
            self._pending_acks.clear()

    def _writer_loop(self) -> None:
        """Drains the write queue and sends tokens fire-and-forget."""
        log.debug("arduino_manager.writer.start", port=self._port)
        while not self._stop_event.is_set():
            try:
                token, context = self._write_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            with self._lock:
                arduino = self.arduino if self.is_connected() else None
            if arduino is None:
                log.debug("arduino_manager.writer.offline", token=token)
                continue

            # Stamp t_send as close to the wire as possible and register the
            # pending trigger BEFORE writing, so a fast ACK can never be read by
            # the reader thread before the pending entry exists.
            t_send = time.perf_counter()
            overflow: list[tuple[float, dict[str, Any]]] = []
            if context is not None:
                with self._latency_lock:
                    if self._latency_sink is not None:
                        self._pending_acks.append((t_send, context))
                        while len(self._pending_acks) > self._max_pending_acks:
                            overflow.append(self._pending_acks.popleft())
            for old_send, old_ctx in overflow:
                self._emit_latency(old_ctx, old_send, None, None)

            try:
                if arduino.send_command_async(token):
                    self._last_command = token
            # except Exception justified: serial write — hardware I/O boundary
            except Exception:
                log.error("arduino_manager.writer.send_error", token=token, exc_info=True)
        log.debug("arduino_manager.writer.stop", port=self._port)

    def _reader_loop(self) -> None:
        """Continuously reads from serial port and dispatches events."""
        log.debug("arduino_manager.reader.start", port=self._port)
        while not self._stop_event.is_set():
            with self._lock:
                arduino = self.arduino if self.is_connected() else None
            if arduino is None:
                time.sleep(0.25)
                continue

            serial_conn = getattr(arduino, "ser", None)
            if not serial_conn:
                time.sleep(0.5)
                continue

            try:
                raw_line = serial_conn.readline()
                t_ack = time.perf_counter()
            except SerialExceptionType:
                log.warning("arduino_manager.reader.serial_exception", exc_info=True)
                self._notify_log("Conexão serial com Arduino perdida.")
                self.disconnect()
                break
            # except Exception justified: serial reader fallback
            except Exception:
                log.warning("arduino_manager.reader.generic_error", exc_info=True)
                time.sleep(0.5)
                continue

            if not raw_line:
                continue

            try:
                decoded = raw_line.decode("utf-8", errors="ignore").strip()
            except (UnicodeDecodeError, AttributeError):
                log.debug("arduino.serial_decode.corrupted_data")
                continue

            if not decoded:
                continue

            if self._is_int(decoded):
                # Numeric inbound lines are genuine device events (sensors,
                # buttons). This firmware ACKs commands with TEXT lines, so a
                # numeric line is never an ACK and must not consume a pending.
                event_code = int(decoded)
                self._dispatch_event(event_code)
            elif not self._consume_ack(decoded, t_ack):
                self._notify_log(f"Arduino: {decoded}")

        log.debug("arduino_manager.reader.stop", port=self._port)

    def _consume_ack(self, ack_text: str, t_ack: float) -> bool:
        """Match a firmware ACK line to the oldest pending tracked send (FIFO).

        Returns True when the line was consumed as an ACK (so the caller skips
        the normal text-log path), False when there is nothing to match (no sink
        or no pending) and the line should be logged as a plain message.
        """
        with self._latency_lock:
            if self._latency_sink is None or not self._pending_acks:
                return False
            t_send, context = self._pending_acks.popleft()
            sink = self._latency_sink
        self._emit_latency(context, t_send, t_ack, ack_text, sink)
        return True

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
