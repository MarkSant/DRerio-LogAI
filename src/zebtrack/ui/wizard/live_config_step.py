"""
Step 3 (Live only): Live Recording Configuration

Configures camera, Arduino, and recording settings for live projects.
"""

from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    DoubleVar,
    Entry,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    Spinbox,
    StringVar,
)
from tkinter import (
    font as tkfont,
)

import structlog

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()


class LiveConfigStep(WizardStep):
    """
    Live Configuration step - configure camera and recording settings.

    Questions:
        - Which camera to use?
        - Use Arduino for synchronization?
        - Recording duration settings
        - Countdown settings

    Output:
        {
            "camera_index": int,
            "use_arduino": bool,
            "arduino_port": str | None,
            "use_timed_recording": bool,
            "recording_duration_s": float,
            "use_countdown": bool,
            "countdown_duration_s": int,
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize live config step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.LIVE_CONFIG

        # UI state
        self.camera_index_var = IntVar(value=0)
        self.use_arduino_var = BooleanVar(value=False)
        self.arduino_port_var = StringVar(value="")
        self.use_timed_recording_var = BooleanVar(value=True)
        self.recording_duration_var = DoubleVar(value=300.0)  # 5 minutes default
        self.use_countdown_var = BooleanVar(value=True)
        self.countdown_duration_var = IntVar(value=10)

        # Available cameras and Arduino ports (populated on show)
        self.available_cameras = []
        self.available_ports = []
        self.template_info_var = StringVar(value="")
        self.template_info_label = None

    def build_ui(self):
        """Build live configuration UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Configuração de Gravação ao Vivo", font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Configure a câmera e as opções de gravação para o projeto ao vivo.",
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=500,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Camera configuration
        camera_frame = LabelFrame(self, text="Configuração de Câmera", padx=15, pady=10)
        camera_frame.pack(fill="x", pady=(0, 15))

        # Camera index
        camera_row = Frame(camera_frame)
        camera_row.pack(fill="x", pady=5)

        Label(
            camera_row,
            text="Índice da Câmera:",
            width=25,
            anchor="w",
        ).pack(side="left")
        camera_spinbox = Spinbox(
            camera_row,
            from_=0,
            to=10,
            textvariable=self.camera_index_var,
            width=10,
        )
        camera_spinbox.pack(side="left", padx=(5, 0))
        ToolTip(
            camera_spinbox,
            ("Índice da câmera a ser usada (geralmente 0 para câmera padrão)."),
        )

        Button(
            camera_row,
            text="🔍 Detectar Câmeras",
            command=self._detect_cameras,
        ).pack(side="left", padx=10)

        self.camera_status_label = Label(camera_row, text="", fg="gray")
        self.camera_status_label.pack(side="left", padx=5)

        # Arduino configuration
        arduino_frame = LabelFrame(
            self,
            text="Configuração de Arduino (Opcional)",
            padx=15,
            pady=10,
        )
        arduino_frame.pack(fill="x", pady=(0, 15))

        use_arduino_cb = Checkbutton(
            arduino_frame,
            text="Usar Arduino para sincronização",
            variable=self.use_arduino_var,
            command=self._on_arduino_toggle,
        )
        use_arduino_cb.pack(anchor="w", pady=5)
        ToolTip(
            use_arduino_cb,
            ("Habilitar Arduino para sincronizar eventos externos com a gravação."),
        )

        # Arduino port selection
        self.arduino_port_frame = Frame(arduino_frame)
        self.arduino_port_frame.pack(fill="x", pady=5)

        Label(
            self.arduino_port_frame,
            text="Porta do Arduino:",
            width=25,
            anchor="w",
        ).pack(side="left")
        self.arduino_port_entry = Entry(
            self.arduino_port_frame,
            textvariable=self.arduino_port_var,
            width=20,
            state="disabled",
        )
        self.arduino_port_entry.pack(side="left", padx=(5, 5))

        self.detect_arduino_btn = Button(
            self.arduino_port_frame,
            text="🔍 Detectar Portas",
            command=self._detect_arduino_ports,
            state="disabled",
        )
        self.detect_arduino_btn.pack(side="left", padx=5)

        self.arduino_status_label = Label(self.arduino_port_frame, text="", fg="gray")
        self.arduino_status_label.pack(side="left", padx=5)

        # Recording settings
        recording_frame = LabelFrame(
            self,
            text="Configurações de Gravação",
            padx=15,
            pady=10,
        )
        recording_frame.pack(fill="x", pady=(0, 15))

        # Timed recording
        timed_cb = Checkbutton(
            recording_frame,
            text="Usar gravação temporizada",
            variable=self.use_timed_recording_var,
            command=self._on_timed_toggle,
        )
        timed_cb.pack(anchor="w", pady=5)
        ToolTip(
            timed_cb,
            (
                "Habilitar gravação com duração fixa (desliga automaticamente "
                "após o tempo especificado)."
            ),
        )

        self.duration_frame = Frame(recording_frame)
        self.duration_frame.pack(fill="x", pady=5)

        Label(
            self.duration_frame,
            text="Duração da gravação (segundos):",
            width=30,
            anchor="w",
        ).pack(side="left")
        duration_entry = Entry(
            self.duration_frame,
            textvariable=self.recording_duration_var,
            width=10,
        )
        duration_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            duration_entry,
            "Duração total da gravação em segundos (ex: 300 = 5 minutos).",
        )

        # Countdown
        countdown_cb = Checkbutton(
            recording_frame,
            text="Usar contagem regressiva antes de iniciar",
            variable=self.use_countdown_var,
            command=self._on_countdown_toggle,
        )
        countdown_cb.pack(anchor="w", pady=5)
        ToolTip(
            countdown_cb,
            "Mostrar contagem regressiva antes de iniciar a gravação.",
        )

        self.countdown_frame = Frame(recording_frame)
        self.countdown_frame.pack(fill="x", pady=5)

        Label(
            self.countdown_frame,
            text="Duração da contagem (segundos):",
            width=30,
            anchor="w",
        ).pack(side="left")
        countdown_spinbox = Spinbox(
            self.countdown_frame,
            from_=1,
            to=60,
            textvariable=self.countdown_duration_var,
            width=10,
        )
        countdown_spinbox.pack(side="left", padx=(5, 0))
        ToolTip(
            countdown_spinbox,
            "Duração da contagem regressiva em segundos.",
        )

        # Help text
        help_frame = LabelFrame(
            self,
            text="Sobre Projetos ao Vivo",
            padx=15,
            pady=10,
        )
        help_frame.pack(fill="x", pady=(15, 0))

        help_text = Label(
            help_frame,
            text=(
                "Projetos ao vivo gravam diretamente da câmera em tempo real.\n\n"
                "• A câmera deve estar conectada antes de criar o projeto\n"
                "• Arduino é opcional e usado para sincronizar eventos externos\n"
                "• Gravação temporizada desliga automaticamente após o tempo "
                "especificado\n"
                "• Contagem regressiva dá tempo para preparar o experimento\n\n"
                "💡 Dica: Teste a câmera antes de iniciar o projeto para garantir "
                "que está funcionando."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack()

        self._update_template_banner()

    def on_show(self):
        """Called when step becomes visible."""
        self._update_template_banner()
        # Update UI state based on checkboxes
        self._on_arduino_toggle()
        self._on_timed_toggle()
        self._on_countdown_toggle()

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 10))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()

    def _on_arduino_toggle(self):
        """Enable/disable Arduino controls based on checkbox."""
        if self.use_arduino_var.get():
            self.arduino_port_entry.config(state="normal")
            self.detect_arduino_btn.config(state="normal")
        else:
            self.arduino_port_entry.config(state="disabled")
            self.detect_arduino_btn.config(state="disabled")
            self.arduino_port_var.set("")

    def _on_timed_toggle(self):
        """Enable/disable duration controls based on checkbox."""
        if self.use_timed_recording_var.get():
            for widget in self.duration_frame.winfo_children():
                if isinstance(widget, Entry):
                    widget.config(state="normal")
        else:
            for widget in self.duration_frame.winfo_children():
                if isinstance(widget, Entry):
                    widget.config(state="disabled")

    def _on_countdown_toggle(self):
        """Enable/disable countdown controls based on checkbox."""
        if self.use_countdown_var.get():
            for widget in self.countdown_frame.winfo_children():
                if isinstance(widget, Spinbox):
                    widget.config(state="normal")
        else:
            for widget in self.countdown_frame.winfo_children():
                if isinstance(widget, Spinbox):
                    widget.config(state="disabled")

    def _detect_cameras(self):
        """Detect available cameras."""
        import cv2

        self.camera_status_label.config(text="Detectando...", fg="blue")
        self.update_idletasks()

        available = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()

        if available:
            self.camera_status_label.config(
                text=f"✓ {len(available)} câmera(s) detectada(s): {available}",
                fg="green",
            )
            # Auto-select first camera
            if self.camera_index_var.get() not in available:
                self.camera_index_var.set(available[0])
        else:
            self.camera_status_label.config(
                text="✗ Nenhuma câmera detectada",
                fg="red",
            )

        log.info(
            "live_config.cameras_detected",
            count=len(available),
            indices=available,
        )

    def _detect_arduino_ports(self):
        """Detect available Arduino ports."""
        try:
            import serial.tools.list_ports

            self.arduino_status_label.config(text="Detectando...", fg="blue")
            self.update_idletasks()

            ports = list(serial.tools.list_ports.comports())
            if ports:
                port_list = [p.device for p in ports]
                self.arduino_status_label.config(
                    text=f"✓ {len(ports)} porta(s) detectada(s)",
                    fg="green",
                )
                # Auto-select first port
                if not self.arduino_port_var.get():
                    self.arduino_port_var.set(port_list[0])

                log.info(
                    "live_config.arduino_ports_detected",
                    count=len(ports),
                    ports=port_list,
                )
            else:
                self.arduino_status_label.config(
                    text="✗ Nenhuma porta detectada",
                    fg="red",
                )
        except ImportError:
            self.arduino_status_label.config(
                text="✗ pyserial não instalado",
                fg="red",
            )
            log.warning("live_config.pyserial_not_available")

    def validate(self) -> tuple[bool, str]:
        """
        Validate live configuration.

        Returns:
            tuple[bool, str]: (True, "") if all inputs are valid,
                             (False, error_message) otherwise
        """
        try:
            camera_index = self.camera_index_var.get()

            if camera_index < 0:
                return (False, "O índice da câmera deve ser >= 0.")

            if self.use_arduino_var.get():
                arduino_port = self.arduino_port_var.get().strip()
                if not arduino_port:
                    return (
                        False,
                        (
                            "Por favor, especifique a porta do Arduino ou "
                            "desmarque a opção 'Usar Arduino'."
                        ),
                    )

            if self.use_timed_recording_var.get():
                duration = self.recording_duration_var.get()
                if duration <= 0:
                    return (False, "A duração da gravação deve ser maior que zero.")

            if self.use_countdown_var.get():
                countdown = self.countdown_duration_var.get()
                if countdown < 1:
                    return (
                        False,
                        "A duração da contagem deve ser pelo menos 1 segundo.",
                    )

            return (True, "")

        except Exception as e:
            return (False, f"Erro ao validar dados: {str(e)}")

    def get_data(self) -> dict:
        """
        Extract live configuration data.

        Returns:
            dict: Live configuration with keys:
                - camera_index (int)
                - use_arduino (bool)
                - arduino_port (str | None)
                - use_timed_recording (bool)
                - recording_duration_s (float)
                - use_countdown (bool)
                - countdown_duration_s (int)
        """
        arduino_port = self.arduino_port_var.get().strip() if self.use_arduino_var.get() else None

        return {
            "camera_index": self.camera_index_var.get(),
            "use_arduino": self.use_arduino_var.get(),
            "arduino_port": arduino_port,
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": self.recording_duration_var.get(),
            "use_countdown": self.use_countdown_var.get(),
            "countdown_duration_s": self.countdown_duration_var.get(),
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected live config data
        """
        if "camera_index" in data:
            self.camera_index_var.set(data["camera_index"])

        if "use_arduino" in data:
            self.use_arduino_var.set(data["use_arduino"])

        if "arduino_port" in data and data["arduino_port"]:
            self.arduino_port_var.set(data["arduino_port"])

        if "use_timed_recording" in data:
            self.use_timed_recording_var.set(data["use_timed_recording"])

        if "recording_duration_s" in data:
            self.recording_duration_var.set(data["recording_duration_s"])

        if "use_countdown" in data:
            self.use_countdown_var.set(data["use_countdown"])

        if "countdown_duration_s" in data:
            self.countdown_duration_var.set(data["countdown_duration_s"])

        # Update UI state
        self._on_arduino_toggle()
        self._on_timed_toggle()
        self._on_countdown_toggle()
