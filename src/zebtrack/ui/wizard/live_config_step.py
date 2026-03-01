"""
Step 3 (Live only): Live Recording Configuration.

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
    messagebox,
    ttk,
)
from tkinter import (
    font as tkfont,
)
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.recording.live_camera_mode import (
    LiveCameraMode,
    LiveCameraModeRecommendation,
    LiveCameraModeSelector,
)
from zebtrack.core.services.wizard_service import WizardService
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip
from zebtrack.utils.hardware_capability import (
    HardwareCapabilityDetector,
    HardwareCapabilityReport,
    MultiAquariumCapability,
)

if TYPE_CHECKING:
    from zebtrack.settings import Settings

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

    def __init__(
        self,
        parent: "Frame",
        wizard_data: dict[str, Any],
        settings_obj: "Settings | None" = None,
    ):
        """Initialize live config step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.LIVE_CONFIG
        self.settings_obj = settings_obj

        # UI state
        self.camera_selection_var = StringVar(value="")  # Stores camera display name
        self.camera_index_map: dict[str, int] = {}  # Maps display name -> camera index
        self.use_arduino_var = BooleanVar(value=False)
        self.arduino_port_var = StringVar(value="")
        self.external_trigger_mode_var = BooleanVar(value=False)
        self.use_timed_recording_var = BooleanVar(value=True)
        self.recording_duration_var = DoubleVar(value=300.0)  # 5 minutes default
        self.use_countdown_var = BooleanVar(value=True)
        self.countdown_duration_var = IntVar(value=10)
        # Processing intervals
        self.analysis_interval_var = IntVar(value=10)
        self.display_interval_var = IntVar(value=10)

        # Experimental design metadata (v2.3.0)
        self.experimental_group_var = StringVar(value="")  # "Controle", "Tratado", etc.
        self.experiment_day_var = StringVar(value="")  # "Dia_1", "Dia_2", etc.
        self.subject_id_var = StringVar(value="")  # "Peixe_01", "Peixe_02", etc.
        self.is_batch_last_session_var = BooleanVar(value=False)  # Mark as final session

        # Available cameras and Arduino ports (populated on show)
        self.available_cameras: list[dict[str, Any]] = []
        self.available_ports: list[dict[str, Any]] = []
        self.arduino_port_map: dict[str, str] = {}  # Maps display name -> port device
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None

        # Hardware capability (v2.2.0)
        self.hardware_report: HardwareCapabilityReport | None = None
        self.selected_mode: LiveCameraMode | None = None

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
        if self.template_info_label:
            self.template_info_label.pack_forget()

        # Camera configuration
        camera_frame = LabelFrame(self, text="Configuração de Câmera", padx=15, pady=10)
        camera_frame.pack(fill="x", pady=(0, 15))

        # Camera selection
        camera_row = Frame(camera_frame)
        camera_row.pack(fill="x", pady=5)

        Label(
            camera_row,
            text="Selecionar Câmera:",
            width=25,
            anchor="w",
        ).pack(side="left")

        self.camera_combo = ttk.Combobox(
            camera_row,
            textvariable=self.camera_selection_var,
            width=40,
            state="readonly",
        )
        self.camera_combo.pack(side="left", padx=(5, 10))
        ToolTip(
            self.camera_combo,
            ("Selecione a câmera para gravação ao vivo."),
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

        # Combobox for Arduino port selection with descriptions
        self.arduino_port_combo = ttk.Combobox(
            self.arduino_port_frame,
            textvariable=self.arduino_port_var,
            width=35,
            state="disabled",
        )
        self.arduino_port_combo.pack(side="left", padx=(5, 5))

        self.detect_arduino_btn = Button(
            self.arduino_port_frame,
            text="🔍 Detectar",
            command=self._detect_arduino_ports,
            state="disabled",
            width=10,
        )
        self.detect_arduino_btn.pack(side="left", padx=2)

        self.test_arduino_btn = Button(
            self.arduino_port_frame,
            text="🔌 Testar",
            command=self._test_arduino_connection,
            state="disabled",
            width=10,
        )
        self.test_arduino_btn.pack(side="left", padx=2)

        self.arduino_status_label = Label(self.arduino_port_frame, text="", fg="gray")
        self.arduino_status_label.pack(side="left", padx=5)

        # External trigger mode
        self.external_trigger_cb = Checkbutton(
            arduino_frame,
            text="Modo de Gatilho Externo (External Trigger)",
            variable=self.external_trigger_mode_var,
            state="disabled",
        )
        self.external_trigger_cb.pack(anchor="w", pady=5)
        ToolTip(
            self.external_trigger_cb,
            (
                "Modo de Gatilho Externo\n\n"
                "Quando habilitado, o Arduino pode controlar início/parada da gravação.\n"
                "Útil para sincronizar gravações com eventos externos ou automação.\n\n"
                "Requer Arduino conectado e configurado."
            ),
        )

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

        # Advanced processing settings
        advanced_frame = LabelFrame(
            self,
            text="⚙️ Configurações Avançadas de Processamento",
            padx=15,
            pady=10,
        )
        advanced_frame.pack(fill="x", pady=(15, 0))

        # Analysis interval
        analysis_row = Frame(advanced_frame)
        analysis_row.pack(fill="x", pady=5)

        Label(
            analysis_row,
            text="Intervalo de Análise (frames):",
            width=30,
            anchor="w",
        ).pack(side="left")
        analysis_spinbox = Spinbox(
            analysis_row,
            from_=1,
            to=100,
            textvariable=self.analysis_interval_var,
            width=10,
        )
        analysis_spinbox.pack(side="left", padx=(5, 0))
        ToolTip(
            analysis_spinbox,
            (
                "Intervalo de Análise (frames)\n\n"
                "Quantos frames aguardar entre detecções.\n"
                "Valores maiores: processamento mais rápido, menos precisão.\n"
                "Valores menores: processamento mais lento, mais precisão.\n\n"
                "Padrão: 10 frames (recomendado para maioria dos casos)"
            ),
        )

        # Display interval
        display_row = Frame(advanced_frame)
        display_row.pack(fill="x", pady=5)

        Label(
            display_row,
            text="Intervalo de Exibição (frames):",
            width=30,
            anchor="w",
        ).pack(side="left")
        display_spinbox = Spinbox(
            display_row,
            from_=1,
            to=100,
            textvariable=self.display_interval_var,
            width=10,
        )
        display_spinbox.pack(side="left", padx=(5, 0))
        ToolTip(
            display_spinbox,
            (
                "Intervalo de Exibição (frames)\n\n"
                "Quantos frames aguardar entre atualizações visuais da interface.\n"
                "Valores maiores: interface mais fluida, menos detalhes visuais.\n"
                "Valores menores: mais detalhes visuais, possível lentidão.\n\n"
                "Padrão: 10 frames (recomendado para maioria dos casos)"
            ),
        )

        # Restore defaults button
        restore_btn = Button(
            advanced_frame,
            text="🔄 Restaurar Padrões (10, 10)",
            command=self._restore_default_intervals,
        )
        restore_btn.pack(fill="x", pady=(10, 0))
        ToolTip(
            restore_btn,
            (
                "Restaura os intervalos para os valores padrão recomendados:\n"
                "• Análise: 10 frames\n"
                "• Exibição: 10 frames\n\n"
                "Estes valores oferecem bom equilíbrio entre desempenho e precisão."
            ),
        )

        # === Experimental Design Section (v2.3.0) ===
        experiment_frame = LabelFrame(
            self,
            text="🧪 Design Experimental (Opcional)",
            padx=15,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        )
        experiment_frame.pack(fill="x", pady=(15, 0))

        # Group field
        group_row = Frame(experiment_frame)
        group_row.pack(fill="x", pady=5)
        Label(
            group_row,
            text="Grupo Experimental:",
            width=30,
            anchor="w",
        ).pack(side="left")
        group_combo = ttk.Combobox(
            group_row,
            textvariable=self.experimental_group_var,
            values=["Controle", "Tratado", "CBD_10mg", "CBD_20mg", "Outro"],
            width=25,
        )
        group_combo.pack(side="left", padx=(5, 0))
        ToolTip(
            group_combo,
            "Grupo experimental desta sessão (ex: Controle, Tratado, CBD_10mg).",
        )

        # Day field
        day_row = Frame(experiment_frame)
        day_row.pack(fill="x", pady=5)
        Label(
            day_row,
            text="Dia do Experimento:",
            width=30,
            anchor="w",
        ).pack(side="left")
        day_combo = ttk.Combobox(
            day_row,
            textvariable=self.experiment_day_var,
            values=[f"Dia_{i}" for i in range(1, 15)],
            width=25,
        )
        day_combo.pack(side="left", padx=(5, 0))
        ToolTip(
            day_combo,
            "Dia do experimento (ex: Dia_1, Dia_2, ..., Dia_14).",
        )

        # Subject ID field
        subject_row = Frame(experiment_frame)
        subject_row.pack(fill="x", pady=5)
        Label(
            subject_row,
            text="ID do Sujeito (Cobaia):",
            width=30,
            anchor="w",
        ).pack(side="left")
        subject_entry = Entry(
            subject_row,
            textvariable=self.subject_id_var,
            width=27,
        )
        subject_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            subject_entry,
            "ID único do sujeito experimental (ex: Peixe_01, Animal_A).",
        )

        # Batch completion checkbox
        batch_check = Checkbutton(
            experiment_frame,
            text="✅ Marcar como última sessão deste lote (gera relatório unificado)",
            variable=self.is_batch_last_session_var,
        )
        batch_check.pack(anchor="w", pady=(10, 5))
        ToolTip(
            batch_check,
            (
                "Marque esta opção se esta é a última sessão do lote experimental.\n\n"
                "Ao marcar, o sistema irá:\n"
                "• Consolidar todas as sessões deste grupo/dia\n"
                "• Gerar um relatório unificado em Excel\n"
                "• Incluir estatísticas agregadas e comparações\n\n"
                "Deixe desmarcado se ainda há mais sessões neste lote."
            ),
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

    def on_show(self) -> None:
        """Execute actions when step becomes visible."""
        self._update_template_banner()
        # Update UI state based on checkboxes
        self._on_arduino_toggle()
        self._on_timed_toggle()
        self._on_countdown_toggle()

        # v2.2.0: Detect hardware capability
        self._detect_hardware_capability()

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

    def _restore_default_intervals(self):
        """Restore processing intervals to default values."""
        self.analysis_interval_var.set(10)
        self.display_interval_var.set(10)

    def _detect_hardware_capability(self) -> None:
        """Detect hardware capability for multi-aquarium processing.

        Runs hardware assessment and stores report for later validation.
        Shows warning if hardware is insufficient for real-time processing.
        """
        try:
            # Use injected settings_obj
            if not self.settings_obj:
                log.warning("live_config.hardware_detection_skipped_no_settings")
                self.hardware_report = None
                return

            detector = HardwareCapabilityDetector(self.settings_obj)
            self.hardware_report = detector.assess_capability()

            log.info(
                "live_config.hardware_detected",
                capability=self.hardware_report.capability.name,
                max_aquariums=self.hardware_report.max_aquariums_recommended,
                can_realtime=self.hardware_report.can_process_realtime,
            )

            # Show info message if hardware is limited/insufficient
            if self.hardware_report.capability in [
                MultiAquariumCapability.LIMITED,
                MultiAquariumCapability.INSUFFICIENT,
            ]:
                msg = (
                    f"Hardware Detectado:\n\n"
                    f"Capacidade: {self.hardware_report.capability.name}\n"
                    f"CPU: {self.hardware_report.cpu_cores} cores\n"
                    f"RAM: {self.hardware_report.available_memory_gb:.1f} GB\n"
                    f"GPU: {'Sim' if self.hardware_report.has_gpu else 'Não'}\n\n"
                )

                if self.hardware_report.capability == MultiAquariumCapability.INSUFFICIENT:
                    msg += (
                        "⚠️ Seu sistema NÃO suporta processamento em tempo real.\n"
                        "Recomendação: Use modo 'Apenas Gravação' (offline)."
                    )
                else:
                    msg += (
                        f"Aquários suportados: {self.hardware_report.max_aquariums_recommended}\n"
                        f"Multi-aquário em tempo real pode não ser possível."
                    )

                messagebox.showinfo("Detecção de Hardware", msg, parent=self)

        except Exception as e:  # except Exception justified: hardware detection multi-library
            log.error("live_config.hardware_detection_failed", error=str(e))
            # Non-critical - continue without hardware report
            self.hardware_report = None

    def _check_mode_compatibility(self, requested_aquariums: int) -> bool:
        """Check if requested aquarium count is compatible with hardware.

        Shows mode selection dialog if hardware insufficient.

        Args:
            requested_aquariums: Number of aquariums from zone config step

        Returns:
            True if mode selected/compatible, False if user cancelled
        """
        if not self.hardware_report:
            # No hardware report - allow proceeding (fail gracefully)
            log.warning("live_config.no_hardware_report")
            return True

        # Use LiveCameraModeSelector to get recommendation
        if not self.settings_obj or not self.hardware_report:
            log.warning("live_config.missing_requirements_for_mode_selection")
            return True

        selector = LiveCameraModeSelector(self.settings_obj)
        recommendation = selector.recommend_mode(
            requested_aquariums=requested_aquariums, hardware_report=self.hardware_report
        )

        # Check if recommended mode is different from multi-aquarium real-time
        if (
            requested_aquariums > 1
            and recommendation.recommended_mode != LiveCameraMode.MULTI_AQUARIUM_REALTIME
        ):
            # Show mode selection dialog
            return self._show_mode_selection_dialog(requested_aquariums, recommendation)
        else:
            # Hardware supports requested config or single aquarium
            self.selected_mode = (
                LiveCameraMode.MULTI_AQUARIUM_REALTIME
                if requested_aquariums > 1
                else LiveCameraMode.SINGLE_AQUARIUM_REALTIME
            )
            return True

    def _show_mode_selection_dialog(
        self, requested_aquariums: int, recommendation: LiveCameraModeRecommendation
    ) -> bool:
        """Show mode selection dialog and wait for user choice.

        Args:
            requested_aquariums: Number of aquariums requested
            recommendation: LiveCameraModeRecommendation from selector

        Returns:
            True if mode selected, False if user cancelled
        """
        from zebtrack.ui.dialogs.live_camera_mode_selection_dialog import (
            LiveCameraModeSelectionDialog,
        )

        mode_selected = [False]  # Mutable flag for callback

        def on_mode_selected(mode: LiveCameraMode) -> None:
            self.selected_mode = mode
            mode_selected[0] = True
            log.info("live_config.mode_selected", mode=mode.name)

        if not self.hardware_report:
            log.warning("live_config.missing_hardware_report")
            return False

        dialog = LiveCameraModeSelectionDialog(
            parent=self,
            requested_aquariums=requested_aquariums,
            hardware_report=self.hardware_report,
            recommendation=recommendation,
            on_mode_selected=on_mode_selected,
        )

        # Wait for dialog to close
        self.wait_window(dialog)

        return mode_selected[0]

    def _on_arduino_toggle(self):
        """Enable/disable Arduino controls based on checkbox."""
        if self.use_arduino_var.get():
            self.arduino_port_combo.config(state="readonly")
            self.detect_arduino_btn.config(state="normal")
            self.test_arduino_btn.config(state="normal")
            self.external_trigger_cb.config(state="normal")
        else:
            self.arduino_port_combo.config(state="disabled")
            self.detect_arduino_btn.config(state="disabled")
            self.test_arduino_btn.config(state="disabled")
            self.external_trigger_cb.config(state="disabled")
            self.arduino_port_var.set("")
            self.external_trigger_mode_var.set(False)

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
        """Detect available cameras using WizardService."""
        self.camera_status_label.config(text="Detectando...", fg="blue")
        self.update_idletasks()

        # Use WizardService for camera detection
        cameras = WizardService.detect_available_cameras()

        if cameras:
            # Build display list with camera names and map to indices
            camera_list = []
            self.camera_index_map.clear()

            for cam in cameras:
                description = cam.get("description", f"Câmera {cam['index']}")
                camera_list.append(description)
                self.camera_index_map[description] = cam["index"]

            # Update combobox
            self.camera_combo["values"] = camera_list

            self.camera_status_label.config(
                text=f"✓ {len(cameras)} câmera(s) detectada(s)",
                fg="green",
            )

            # Auto-select first camera if none selected
            if not self.camera_selection_var.get() and camera_list:
                self.camera_selection_var.set(camera_list[0])
        else:
            self.camera_combo["values"] = []
            self.camera_index_map.clear()
            self.camera_status_label.config(
                text="✗ Nenhuma câmera detectada",
                fg="red",
            )

    def _detect_arduino_ports(self):
        """Detect available Arduino ports using WizardService."""
        try:
            self.arduino_status_label.config(text="Detectando...", fg="blue")
            self.update_idletasks()

            # Use WizardService for Arduino port detection
            ports_info = WizardService.detect_arduino_ports()

            if ports_info:
                # Build display strings using display_name from service
                display_list = [port["display_name"] for port in ports_info]
                self.arduino_port_map.clear()

                for port_info in ports_info:
                    # Map display text to actual device
                    self.arduino_port_map[port_info["display_name"]] = port_info["device"]

                # Update combobox
                self.arduino_port_combo["values"] = display_list

                self.arduino_status_label.config(
                    text=f"✓ {len(ports_info)} porta(s) detectada(s)",
                    fg="green",
                )

                # Auto-select first port if none selected
                if not self.arduino_port_var.get() and display_list:
                    self.arduino_port_var.set(display_list[0])
            else:
                self.arduino_port_combo["values"] = []
                self.arduino_port_map.clear()
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

    def _test_arduino_connection(self):
        """Test Arduino connection with selected port."""
        selected_display = self.arduino_port_var.get()
        if not selected_display:
            messagebox.showwarning(
                "Nenhuma Porta Selecionada",
                "Por favor, detecte e selecione uma porta Arduino primeiro.",
            )
            return

        # Get actual device from mapping
        port_device = self.arduino_port_map.get(selected_display, selected_display)

        try:
            import serial

            self.arduino_status_label.config(text="Testando...", fg="blue")
            self.update_idletasks()

            # Try to open serial connection
            ser = serial.Serial(port_device, 9600, timeout=2)
            ser.close()

            # Success
            self.arduino_status_label.config(text="✓ Conexão OK", fg="green")
            messagebox.showinfo(
                "Teste de Conexão",
                f"Conexão com {port_device} estabelecida com sucesso!\n\n"
                "A porta está acessível e pronta para uso.",
            )

            log.info("live_config.arduino_test_success", port=port_device)

        except serial.SerialException as e:
            self.arduino_status_label.config(text="✗ Falha na conexão", fg="red")
            messagebox.showerror(
                "Erro de Conexão",
                f"Não foi possível conectar à porta {port_device}.\n\n"
                f"Erro: {e!s}\n\n"
                "Verifique se:\n"
                "• O Arduino está conectado\n"
                "• A porta não está em uso por outro programa\n"
                "• Você tem permissão para acessar a porta",
            )
            log.error("live_config.arduino_test_failed", port=port_device, error=str(e))

        except ImportError:
            self.arduino_status_label.config(text="✗ pyserial não disponível", fg="red")
            messagebox.showerror(
                "Erro",
                "A biblioteca pyserial não está instalada.\n\nExecute: pip install pyserial",
            )
            log.warning("live_config.pyserial_not_available")

        except Exception as e:  # except Exception justified: serial port + pyserial multi-error
            self.arduino_status_label.config(text="✗ Erro inesperado", fg="red")
            messagebox.showerror(
                "Erro Inesperado",
                f"Ocorreu um erro ao testar a conexão:\n\n{e!s}",
            )
            log.error("live_config.arduino_test_error", error=str(e))

    def validate(self) -> tuple[bool, str]:
        """
        Validate live configuration using WizardService.

        Returns:
            tuple[bool, str]: (True, "") if all inputs are valid,
                             (False, error_message) otherwise
        """
        try:
            # Get current data
            data = self.get_data()

            # Use WizardService for validation
            is_valid, error_msg = WizardService.validate_live_config(data)

            if not is_valid:
                return (is_valid, error_msg)

            # v2.2.0: Check mode compatibility with zone config
            zone_data = self.wizard_data.get("zone_config", {})
            zones = zone_data.get("zones", [])
            requested_aquariums = len(zones) if zones else 1

            # v2.2.0: Enforce 2-aquarium constraint for live recording
            if requested_aquariums > 2:
                import tkinter.messagebox as messagebox

                messagebox.showwarning(
                    "Limitação de Aquários",
                    f"⚠️ Gravação simultânea limitada a 2 aquários.\n\n"
                    f"Seu projeto tem {requested_aquariums} aquários configurados.\n\n"
                    f"Opções:\n"
                    f"• Reduza para 2 aquários na configuração de zonas\n"
                    f"• Use modo sequencial (processar aquários separadamente)\n"
                    f"• Processe offline após gravação sem detecção",
                )
                return (
                    False,
                    f"Projeto com {requested_aquariums} aquários excede o "
                    f"limite de 2 para gravação simultânea.",
                )

            # Check if hardware supports requested aquarium count
            if not self._check_mode_compatibility(requested_aquariums):
                return (
                    False,
                    "Seleção de modo cancelada. Por favor, ajuste o número "
                    "de aquários ou selecione um modo compatível.",
                )

            # Store selected mode in wizard_data for later use
            if self.selected_mode:
                self.wizard_data["selected_live_mode"] = self.selected_mode.name
                log.info(
                    "live_config.mode_stored",
                    mode=self.selected_mode.name,
                    aquariums=requested_aquariums,
                )

            return (True, "")

        except (ValueError, KeyError, AttributeError) as e:
            return (False, f"Erro ao validar dados: {e!s}")

    def get_data(self) -> dict:
        """
        Extract live configuration data.

        Returns:
            dict: Live configuration with keys:
                - camera_index (int)
                - use_arduino (bool)
                - arduino_port (str | None)
                - external_trigger_mode (bool)
                - use_timed_recording (bool)
                - recording_duration_s (float)
                - use_countdown (bool)
                - countdown_duration_s (int)
        """
        # Get camera index from selected camera name
        selected_camera = self.camera_selection_var.get()
        camera_index = self.camera_index_map.get(selected_camera, 0)

        arduino_port = None
        if self.use_arduino_var.get():
            selected_display = self.arduino_port_var.get().strip()
            if selected_display:
                # Convert display text back to actual device
                arduino_port = self.arduino_port_map.get(selected_display, selected_display)

        return {
            "camera_index": camera_index,
            "use_arduino": self.use_arduino_var.get(),
            "arduino_port": arduino_port,
            "external_trigger_mode": self.external_trigger_mode_var.get(),
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": self.recording_duration_var.get(),
            "use_countdown": self.use_countdown_var.get(),
            "countdown_duration_s": self.countdown_duration_var.get(),
            "analysis_interval_frames": self.analysis_interval_var.get(),
            "display_interval_frames": self.display_interval_var.get(),
            # v2.2.0: Include selected mode for coordinator integration
            "selected_live_mode": self.wizard_data.get("selected_live_mode"),
            # v2.3.0: Experimental design metadata for batch tracking
            "experimental_group": self.experimental_group_var.get() or None,
            "experiment_day": self.experiment_day_var.get() or None,
            "subject_id": self.subject_id_var.get() or None,
            "is_batch_last_session": self.is_batch_last_session_var.get(),
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected live config data
        """
        self._restore_camera(data)
        self._restore_arduino(data)
        self._restore_recording_settings(data)
        self._restore_advanced_settings(data)
        self._restore_batch_metadata(data)

        # Update UI state
        self._on_arduino_toggle()
        self._on_timed_toggle()
        self._on_countdown_toggle()

    def _restore_camera(self, data: dict):
        """Restore camera selection."""
        if "camera_index" in data:
            camera_idx = data["camera_index"]
            for display_name, idx in self.camera_index_map.items():
                if idx == camera_idx:
                    self.camera_selection_var.set(display_name)
                    break

    def _restore_arduino(self, data: dict):
        """Restore Arduino settings."""
        if "use_arduino" in data:
            self.use_arduino_var.set(data["use_arduino"])

        if "external_trigger_mode" in data:
            self.external_trigger_mode_var.set(data["external_trigger_mode"])

        if not data.get("arduino_port"):
            return

        port_device = data["arduino_port"]
        for display, device in self.arduino_port_map.items():
            if device == port_device:
                self.arduino_port_var.set(display)
                return

        # Fallback: set the raw device
        self.arduino_port_var.set(port_device)

    def _restore_recording_settings(self, data: dict):
        """Restore recording configuration."""
        if "use_timed_recording" in data:
            self.use_timed_recording_var.set(data["use_timed_recording"])

        if "recording_duration_s" in data:
            self.recording_duration_var.set(data["recording_duration_s"])

        if "use_countdown" in data:
            self.use_countdown_var.set(data["use_countdown"])

        if "countdown_duration_s" in data:
            self.countdown_duration_var.set(data["countdown_duration_s"])

    def _restore_advanced_settings(self, data: dict):
        """Restore advanced processing intervals."""
        if "analysis_interval_frames" in data:
            self.analysis_interval_var.set(data["analysis_interval_frames"])

        if "display_interval_frames" in data:
            self.display_interval_var.set(data["display_interval_frames"])

    def _restore_batch_metadata(self, data: dict):
        """Restore experimental design metadata."""
        if "experimental_group" in data:
            self.experimental_group_var.set(data["experimental_group"] or "")

        if "experiment_day" in data:
            self.experiment_day_var.set(data["experiment_day"] or "")

        if "subject_id" in data:
            self.subject_id_var.set(data["subject_id"] or "")

        if "is_batch_last_session" in data:
            self.is_batch_last_session_var.set(data["is_batch_last_session"])
