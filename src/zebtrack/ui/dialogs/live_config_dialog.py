"""
Dialog for configuring live analysis settings (camera and Arduino).

This dialog allows users to select a camera and optionally configure Arduino
hardware for live tracking sessions.
"""

# Standard library imports
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Frame,
    Label,
    StringVar,
    messagebox,
    simpledialog,
    ttk,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings

# Third-party imports
import serial.tools.list_ports
import structlog

# Local imports
from zebtrack.io.arduino import Arduino

log = structlog.get_logger()


class LiveConfigDialog(simpledialog.Dialog):
    """A dialog to configure live analysis settings (camera and Arduino)."""

    def __init__(self, parent, settings_obj: "Settings | None" = None):
        """Initialize the live configuration dialog.

        Args:
            parent: Parent widget.
            settings_obj: Settings object with configuration.
        """
        self.result = None
        self.available_cameras = {}
        self.available_ports = {}
        self.settings_obj = settings_obj
        super().__init__(parent, "Configuração da Análise ao Vivo")

    def body(self, master):
        """Create dialog body with live analysis configuration controls.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        # --- Detect devices first ---
        self._detect_devices()

        # --- Tkinter Variables ---
        self.camera_var = StringVar()
        self.use_arduino_var = BooleanVar(value=True)
        self.arduino_port_var = StringVar()

        # --- Camera Selection ---
        camera_frame = Frame(master)
        camera_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        Label(camera_frame, text="Selecionar Câmera:").pack(side="left", padx=(0, 5))

        self.camera_combo = ttk.Combobox(
            camera_frame, textvariable=self.camera_var, width=40, state="readonly"
        )
        self.camera_combo.pack(side="left", padx=5)

        Button(camera_frame, text="🔍 Detectar", command=self._refresh_cameras, width=10).pack(
            side="left", padx=5
        )

        camera_names = list(self.available_cameras.keys())
        if camera_names:
            self.camera_combo["values"] = camera_names
            self.camera_var.set(camera_names[0])
        else:
            self.camera_combo["values"] = ["Nenhuma câmera encontrada"]
            self.camera_combo.config(state="disabled")

        # --- Arduino Selection ---
        self.arduino_check = Checkbutton(
            master,
            text="Usar Arduino",
            variable=self.use_arduino_var,
            command=self._toggle_arduino_menu,
        )
        self.arduino_check.grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        arduino_frame = Frame(master)
        arduino_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        Label(arduino_frame, text="Porta Arduino:").pack(side="left", padx=(0, 5))

        self.arduino_combo = ttk.Combobox(
            arduino_frame, textvariable=self.arduino_port_var, width=40, state="disabled"
        )
        self.arduino_combo.pack(side="left", padx=5)

        port_names = list(self.available_ports.keys())
        if port_names:
            self.arduino_combo["values"] = port_names
            self.arduino_port_var.set(port_names[0])
        else:
            self.arduino_combo["values"] = ["Nenhuma porta encontrada"]

        self._toggle_arduino_menu()  # Set initial state
        return self.camera_combo  # Initial focus

    def _refresh_cameras(self):
        """Refresh camera list on user request."""
        from zebtrack.core.wizard_service import WizardService

        # Clear cache and re-detect
        self.available_cameras.clear()
        cameras = WizardService.detect_available_cameras(use_cache=False)

        for camera in cameras:
            description = camera.get("description", f"Câmera {camera['index']}")
            self.available_cameras[description] = camera["index"]

        # Update combobox
        camera_names = list(self.available_cameras.keys())
        if camera_names:
            self.camera_combo["values"] = camera_names
            self.camera_combo.config(state="readonly")
            # Keep current selection if still valid, otherwise select first
            current = self.camera_var.get()
            if current not in camera_names:
                self.camera_var.set(camera_names[0])
        else:
            self.camera_combo["values"] = ["Nenhuma câmera encontrada"]
            self.camera_combo.config(state="disabled")
            self.camera_var.set("Nenhuma câmera encontrada")

        log.info("device_detection.camera.refreshed", cameras=self.available_cameras)

    def _detect_devices(self):
        """Detect available cameras and serial ports."""
        # Import here to access WizardService camera detection
        from zebtrack.core.wizard_service import WizardService

        # Use WizardService to detect cameras (includes real names)
        log.info("device_detection.camera.start")
        cameras = WizardService.detect_available_cameras(use_cache=False)

        for camera in cameras:
            description = camera.get("description", f"Câmera {camera['index']}")
            self.available_cameras[description] = camera["index"]

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
            self.arduino_combo.config(state="readonly")
        else:
            self.arduino_combo.config(state="disabled")
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
