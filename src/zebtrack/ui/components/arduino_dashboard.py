"""
Arduino dashboard widget component - hardware monitoring and control.

Provides real-time monitoring of Arduino hardware connection, event logging,
and port configuration management for live tracking sessions.
"""

# Standard library imports
import time
from dataclasses import is_dataclass
from tkinter import Label, StringVar, Text, messagebox, simpledialog, ttk
from typing import Any

# Third-party imports
import serial.tools.list_ports
import structlog

# Local imports
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

log = structlog.get_logger()


def _payload_get(payload: Any, key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    if is_dataclass(payload) and not isinstance(payload, type):
        return getattr(payload, key, default)
    return default


class ArduinoDashboardWidget(BaseWidget):
    """
    Reusable Arduino dashboard widget for hardware monitoring.

    Provides:
    - Connection status indicator (connected/disconnected)
    - Last command sent display
    - Event log with timestamps (max 300 lines)
    - Port rechecking functionality
    - Clear log button

    Events emitted:
    - arduino.port_update_requested: User selected a new port (payload: {"port": str})
    """

    MAX_LOG_LINES = 300  # Maximum number of lines to keep in the event log

    def __init__(
        self,
        parent,
        event_bus: EventBusV2 | None = None,
        project_manager=None,
        arduino_manager=None,
        **kwargs,
    ):
        """
        Initialize the Arduino dashboard widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            project_manager: Optional project manager for updating configuration
            arduino_manager: Optional ArduinoManager, used to seed the initial
                status from the live connection state (the panel is often built
                AFTER the serial connection was established on project load, so
                relying only on future status events would leave the dot red).
            **kwargs: Additional arguments passed to BaseWidget
        """
        # Store project manager reference for port updates
        self.project_manager = project_manager
        self.arduino_manager = arduino_manager

        # State variables
        self.status_var = StringVar(value="Desconectado")
        self.last_command_var = StringVar(value="-")

        # Widget references
        self.status_indicator: Label | None = None
        self.log_text: Text | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

        # Subscribe to Arduino status + command updates
        if self.event_bus:
            self.event_bus.subscribe(
                UIEvents.UI_UPDATE_ARDUINO_STATUS,
                lambda data: self.update_status(
                    bool(_payload_get(data, "connected", False)),
                    _payload_get(data, "port"),
                ),
            )
            self.event_bus.subscribe(
                UIEvents.UI_UPDATE_ARDUINO_COMMAND,
                lambda data: self.set_last_command(str(_payload_get(data, "command", "-"))),
            )

        # Initialize dashboard state
        self._initialize_state()

    def _build_ui(self) -> None:
        """Build the Arduino dashboard widget UI."""
        # Main frame (LabelFrame)
        main_frame = ttk.LabelFrame(self, text="Dashboard Arduino", padding=10)
        main_frame.pack(fill="both", expand=True)

        # Status row
        self._build_status_row(main_frame)

        # Separator
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=(8, 6))

        # Log section
        self._build_log_section(main_frame)

        # Controls row
        self._build_controls_row(main_frame)

    def _build_status_row(self, parent) -> None:
        """Build the status indicator and last command display."""
        status_row = ttk.Frame(parent)
        status_row.pack(fill="x", pady=2)

        # Status indicator (colored circle)
        self.status_indicator = Label(
            status_row,
            text="●",
            font=("Segoe UI", 12, "bold"),
            foreground="#b91c1c",  # Default: disconnected (red)
        )
        self.status_indicator.pack(side="left")

        # Status text
        ttk.Label(status_row, textvariable=self.status_var).pack(side="left", padx=(6, 12))

        # Last command
        ttk.Label(status_row, text="Último comando:").pack(side="left")
        ttk.Label(status_row, textvariable=self.last_command_var).pack(side="left", padx=(6, 0))

    def _build_log_section(self, parent) -> None:
        """Build the event log display area."""
        ttk.Label(parent, text="Eventos recentes:").pack(anchor="w")

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))

        # Text widget for log display
        self.log_text = Text(
            log_frame,
            height=6,
            wrap="word",
            state="disabled",
            background="#1f2933",
            foreground="#f0f4f8",
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_controls_row(self, parent) -> None:
        """Build the control buttons row."""
        controls_row = ttk.Frame(parent)
        controls_row.pack(fill="x", pady=(6, 0))

        ttk.Button(controls_row, text="Limpar Log", command=self.clear_log).pack(
            side="right", padx=(5, 0)
        )

        ttk.Button(
            controls_row,
            text="🔄 Reverificar Portas",
            command=self._on_recheck_ports_clicked,
        ).pack(side="right")

    def _initialize_state(self) -> None:
        """Initialize the dashboard, seeding status from the live connection.

        The panel is usually built after the Arduino connected on project load,
        so we reflect the manager's current state instead of assuming
        disconnected — otherwise the dot would stay red until the next status
        event, which may never come for an already-established connection.
        """
        self.clear_log()
        self.set_last_command("-")

        connected = False
        port: str | None = None
        manager = self.arduino_manager
        if manager is not None:
            try:
                connected = bool(manager.is_connected())
                if connected and hasattr(manager, "current_port"):
                    port = manager.current_port()
            # except Exception justified: hardware state probe must not break UI build.
            except Exception:
                log.debug("arduino_dashboard.seed_status.suppressed", exc_info=True)
                connected = False
                port = None

        self.update_status(connected=connected, port=port)
        if connected:
            self.append_log(f"Arduino conectado ({port})" if port else "Arduino conectado")

    # Event handlers

    def _on_recheck_ports_clicked(self) -> None:
        """Handle the 'Reverificar Portas' button click."""
        self._recheck_arduino_ports()

    def _recheck_arduino_ports(self) -> None:
        """
        Recheck available Arduino ports and update project configuration.

        Scans for available serial ports and allows updating the Arduino port
        configuration for live projects.
        """
        try:
            # Scan for available ports
            ports = list(serial.tools.list_ports.comports())

            if not ports:
                messagebox.showwarning(
                    "Nenhuma Porta Detectada",
                    "Nenhuma porta serial foi detectada.\n\n"
                    "Verifique se:\n"
                    "• O Arduino está conectado via USB\n"
                    "• Os drivers estão instalados corretamente\n"
                    "• A porta não está sendo usada por outro programa",
                )
                self.append_log("✗ Reverificação: Nenhuma porta detectada")
                return

            # Build display strings with descriptions
            port_options = []
            for port in ports:
                description = port.description or "Dispositivo Serial"
                port_options.append(f"{port.device} - {description}")

            # Show selection dialog
            selection = simpledialog.askstring(
                "Selecionar Porta Arduino",
                f"Detectadas {len(ports)} porta(s) serial.\n\n"
                f"Portas disponíveis:\n" + "\n".join(f"• {opt}" for opt in port_options) + "\n\n"
                "Digite o nome da porta (ex: COM3):",
                initialvalue=ports[0].device if ports else "",
            )

            if selection:
                # Extract device name (strip description if pasted)
                selected_device = selection.split(" - ")[0].strip()

                # Validate selection
                valid_devices = [p.device for p in ports]
                if selected_device not in valid_devices:
                    messagebox.showerror(
                        "Porta Inválida",
                        f"A porta '{selected_device}' não está entre as portas detectadas.\n\n"
                        f"Portas válidas: {', '.join(valid_devices)}",
                    )
                    return

                # Update project configuration (if project_manager is available)
                if self.project_manager and self.project_manager.project_data:
                    old_port = self.project_manager.project_data.get("arduino_port")
                    self.project_manager.project_data["arduino_port"] = selected_device
                    self.project_manager.save_project()

                    # Log update (no blocking dialog)
                    self.append_log(
                        f"✓ Porta atualizada: {old_port or 'Nenhuma'} → {selected_device}"
                    )
                    self.append_log("  Reconectando o Arduino na nova porta...")

                    log.info(
                        "arduino.port_updated",
                        old_port=old_port,
                        new_port=selected_device,
                    )

                    # Emit event to notify controller
                    self.emit_event(
                        UIEvents.ARDUINO_PORT_UPDATE_REQUESTED,
                        {"port": selected_device, "old_port": old_port},
                    )
                else:
                    messagebox.showwarning(
                        "Projeto Não Carregado",
                        "Nenhum projeto está carregado no momento.",
                    )

        except ImportError:
            messagebox.showerror(
                "Erro",
                "A biblioteca pyserial não está instalada.\n\nExecute: pip install pyserial",
            )
            self.append_log("✗ pyserial não disponível")

        except Exception as e:
            messagebox.showerror(
                "Erro",
                f"Ocorreu um erro ao reverificar portas:\n\n{e!s}",
            )
            self.append_log(f"✗ Erro na reverificação: {e!s}")
            log.error("arduino.recheck_ports_failed", error=str(e))

    # Public API for updating widget state

    def append_log(self, message: str) -> None:
        """
        Append a timestamped message to the event log.

        Thread-safe: Schedules UI updates via root.after() to ensure all
        Text widget modifications happen on the main thread, as required by CLAUDE.md.

        Args:
            message: Log message to append
        """
        if not self.log_text:
            return

        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"

        def _update_log():
            """Update log text widget on main thread."""
            if not self.log_text:
                return

            self.log_text.configure(state="normal")
            self.log_text.insert("end", entry)

            try:
                # Trim log to max lines defined by MAX_LOG_LINES
                current_line = int(float(self.log_text.index("end-1c").split(".")[0]))
                if current_line > self.MAX_LOG_LINES:
                    start_line = current_line - self.MAX_LOG_LINES
                    self.log_text.delete("1.0", f"{start_line}.0")
            except Exception:
                # If parsing fails, ignore trimming and keep log growing temporarily
                log.debug("arduino_dashboard.log_trim.suppressed", exc_info=True)

            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        # Schedule UI update on main thread
        # Try multiple approaches for maximum compatibility
        try:
            # First try: use winfo_toplevel() which usually works
            top = self.winfo_toplevel()
            top.after(0, _update_log)
        except (RuntimeError, AttributeError):
            # Second try: direct widget .after() call
            try:
                self.after(0, _update_log)
            except Exception:
                # Widget not ready or mainloop not running - silently skip
                log.debug("arduino_dashboard.schedule_log_update.suppressed", exc_info=True)

    def update_status(self, connected: bool, port: str | None) -> None:
        """
        Update the connection status indicator.

        Args:
            connected: Whether Arduino is connected
            port: Serial port name (e.g., "COM3")
        """
        status_text = "Desconectado"
        if connected and port:
            status_text = f"Conectado ({port})"
        elif connected:
            status_text = "Conectado"

        try:
            self.status_var.set(status_text)
        except Exception:
            log.debug("arduino_dashboard.status_var_set.suppressed", exc_info=True)

        if self.status_indicator:
            color = "#16a34a" if connected else "#b91c1c"  # Green or red
            try:
                self.status_indicator.config(foreground=color)
            except Exception:
                log.debug("arduino_dashboard.status_indicator_config.suppressed", exc_info=True)

    def set_last_command(self, command: str) -> None:
        """
        Update the last command display.

        Args:
            command: Command text to display
        """
        try:
            self.last_command_var.set(command or "-")
        except Exception:
            log.debug("arduino_dashboard.last_command_set.suppressed", exc_info=True)

    def clear_log(self) -> None:
        """Clear all log entries."""
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
