"""
Dialog for configuring live analysis settings (camera and Arduino).

This dialog allows users to select a camera and optionally configure Arduino
hardware for live tracking sessions.
"""

# Standard library imports
from tkinter import BooleanVar, Checkbutton, Label, OptionMenu, StringVar, messagebox, simpledialog
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.settings import Settings

# Third-party imports
import cv2
import serial.tools.list_ports
import structlog

# Local imports
from zebtrack.io.arduino import Arduino

log = structlog.get_logger()


class LiveConfigDialog(simpledialog.Dialog):
    """A dialog to configure live analysis settings (camera and Arduino)."""

    def __init__(self, parent, settings_obj: "Settings | None" = None):
        self.result = None
        self.available_cameras = {}
        self.available_ports = {}
        self.settings_obj = settings_obj
        super().__init__(parent, "Configuração da Análise ao Vivo")

    def body(self, master):
        # --- Detect devices first ---
        self._detect_devices()

        # --- Tkinter Variables ---
        self.camera_var = StringVar()
        self.use_arduino_var = BooleanVar(value=True)
        self.arduino_port_var = StringVar()

        # --- Camera Selection ---
        Label(master, text="Selecionar Câmera:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        camera_names = list(self.available_cameras.keys())
        if not camera_names:
            camera_names = ["Nenhuma câmera encontrada"]
        self.camera_menu = OptionMenu(master, self.camera_var, *camera_names)
        self.camera_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        if self.available_cameras:
            self.camera_var.set(next(iter(self.available_cameras.keys())))
        else:
            self.camera_menu.config(state="disabled")

        # --- Arduino Selection ---
        self.arduino_check = Checkbutton(
            master,
            text="Usar Arduino",
            variable=self.use_arduino_var,
            command=self._toggle_arduino_menu,
        )
        self.arduino_check.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        Label(master, text="Porta Arduino:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        port_names = list(self.available_ports.keys())
        if not port_names:
            port_names = ["Nenhuma porta encontrada"]
        self.arduino_menu = OptionMenu(master, self.arduino_port_var, *port_names)
        self.arduino_menu.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        if self.available_ports:
            self.arduino_port_var.set(next(iter(self.available_ports.keys())))

        self._toggle_arduino_menu()  # Set initial state
        return self.camera_menu  # Initial focus

    def _detect_devices(self):
        """Detects available cameras and serial ports."""
        # Detect cameras with early stopping optimization
        log.info("device_detection.camera.start")
        consecutive_failures = 0
        max_consecutive_failures = 3  # Stop after 3 consecutive failures

        for i in range(10):  # Check up to 10 indices
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    self.available_cameras[f"Câmera {i}"] = i
                    cap.release()
                    consecutive_failures = 0  # Reset counter on success
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures and self.available_cameras:
                        # Stop early if we found at least one camera and hit N consecutive failures
                        log.info(
                            "device_detection.camera.early_stop",
                            last_index=i,
                            reason=f"{consecutive_failures} consecutive failures",
                        )
                        break
            except Exception as e:
                log.warning("device_detection.camera.error", index=i, error=str(e))
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures and self.available_cameras:
                    break
        log.info("device_detection.camera.found", cameras=self.available_cameras)

        # Detect serial ports
        try:
            log.info("device_detection.ports.start")
            # Get baud_rate from injected settings
            baud_rate = 9600  # default
            if self.settings_obj and hasattr(self.settings_obj, "arduino"):
                baud_rate = getattr(self.settings_obj.arduino, "baud_rate", 9600)
            handshake_ports, fallback_ports = Arduino.scan_available_ports(baud_rate=baud_rate)

            def _add_port(info, *, handshake: bool) -> None:
                device_id = getattr(info, "device", None)
                if not device_id:
                    return
                description = getattr(info, "description", device_id)
                suffix = " [Arduino]" if handshake else ""
                if handshake_ports and not handshake:
                    suffix = " [sem handshake]"
                label = f"{description} ({device_id}){suffix}"
                self.available_ports[label] = device_id

            for port in handshake_ports:
                _add_port(port, handshake=True)

            if handshake_ports:
                for port in fallback_ports:
                    _add_port(port, handshake=False)
            else:
                if not fallback_ports:
                    # Ensure we still list raw ports if probe yielded nothing
                    try:
                        fallback_ports = list(serial.tools.list_ports.comports())
                    except Exception:  # pragma: no cover - already logged above
                        fallback_ports = []
                for port in fallback_ports:
                    _add_port(port, handshake=False)

            log.info(
                "device_detection.ports.found",
                ports=self.available_ports,
                recognized=len(handshake_ports),
            )
        except Exception as e:
            log.warning("device_detection.ports.error", error=str(e))
            self.available_ports = {}

    def _toggle_arduino_menu(self):
        """Enable or disable the Arduino port dropdown based on the checkbox."""
        if self.use_arduino_var.get() and self.available_ports:
            self.arduino_menu.config(state="normal")
        else:
            self.arduino_menu.config(state="disabled")
            if not self.available_ports:
                self.use_arduino_var.set(False)

    def validate(self):
        """Validate the inputs before closing the dialog."""
        if not self.available_cameras:
            messagebox.showerror(
                "Erro",
                "Nenhuma câmera detectada. Não é possível iniciar uma sessão ao vivo.",
            )
            return 0
        if self.use_arduino_var.get() and not self.available_ports:
            messagebox.showerror(
                "Erro",
                "O Arduino está ativado, mas nenhuma porta serial foi "
                "encontrada. Por favor, verifique a conexão ou desative a "
                "opção 'Usar Arduino'.",
            )
            return 0
        return 1

    def apply(self):
        """Process the data and set the result."""
        use_arduino = self.use_arduino_var.get()
        selected_port_key = self.arduino_port_var.get()
        self.result = {
            "camera_index": self.available_cameras.get(self.camera_var.get()),
            "use_arduino": use_arduino,
            "arduino_port": self.available_ports.get(selected_port_key) if use_arduino else None,
        }
