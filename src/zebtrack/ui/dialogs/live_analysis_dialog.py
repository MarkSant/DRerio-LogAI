"""
Dialog for configuring and starting live camera analysis sessions.

This dialog allows users to:
- Select a camera device
- Set analysis duration
- Configure analysis parameters
- Start immediate analysis from camera feed
"""

from pathlib import Path
from tkinter import (
    BooleanVar,
    Button,
    DoubleVar,
    Frame,
    IntVar,
    Label,
    Spinbox,
    StringVar,
    messagebox,
    ttk,
)
from tkinter.simpledialog import Dialog
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.core.recording.live_output_paths import default_live_sessions_dir
from zebtrack.core.services.wizard_service import WizardService
from zebtrack.i18n import _
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label

log = structlog.get_logger()


class LiveAnalysisDialog(Dialog):
    """
    Dialog for configuring live camera analysis sessions.

    Provides an interface to:
    - Detect and select available cameras
    - Set analysis duration and intervals
    - Configure recording options
    - Configure calibration parameters
    - Configure behavioral analysis parameters
    - Configure trajectory smoothing
    - Configure detection methods
    - Start immediate analysis

    Result:
        dict with keys:
            - camera_index: int
            - duration_s: float
            - analysis_interval_frames: int
            - display_interval_frames: int
            - record_video: bool
            - use_countdown: bool
            - countdown_duration_s: int
            - output_folder: str | None  (None = the default sessions folder)
            - experiment_id: str
            - num_aquariums: int
            - animals_per_aquarium: int
            - aquarium_width_cm: float
            - aquarium_height_cm: float
            - sharp_turn_threshold_deg_s: float
            - freezing_velocity_threshold: float
            - freezing_min_duration_s: float
            - smoothing_window_length: int
            - smoothing_polyorder: int
            - aquarium_method: str
            - animal_method: str
            - use_openvino: bool
            - use_single_subject_tracker: bool
            - behavioral_analysis: dict
        or None if cancelled
    """

    def __init__(
        self,
        parent: Any,
        settings_obj: "Settings | None" = None,
        event_bus: "EventBusV2 | None" = None,
    ) -> None:
        """
        Initialize live analysis dialog.

        Args:
            parent: Parent Tkinter widget
            settings_obj: Settings instance for defaults
            event_bus: Optional event bus instance
        """
        self.settings = settings_obj
        self.event_bus = event_bus
        self.result: dict[str, Any] | None = None
        self.behavioral_config_widget: BehavioralConfigWidget | None = None

        # UI state
        self.camera_selection_var = StringVar(value="")
        self.camera_index_map: dict[str, int] = {}
        self.duration_var = DoubleVar(
            value=settings_obj.live_analysis.default_duration_s if settings_obj else 300.0
        )
        self.analysis_interval_var = IntVar(value=5)
        self.display_interval_var = IntVar(value=5)
        self.record_video_var = BooleanVar(value=True)
        # Contagem regressiva antes de gravar: OPT-IN (default desligado). O
        # laco de contagem bombeia o event loop do Tk enquanto espera, entao e
        # oferecido, nao imposto. A duracao vem das settings.
        self.use_countdown_var = BooleanVar(value=False)
        self._countdown_seconds = int(
            getattr(getattr(settings_obj, "live_analysis", None), "countdown_duration_s", 5) or 5
        )
        self.experiment_id_var = StringVar(value="")
        # Pasta de saída escolhida pelo usuário. Nasce PREENCHIDA com o padrão
        # (``~/ZebTrack/live_analysis_sessions``) em vez de vazia: um campo em
        # branco não dizia onde a gravação ia parar, e a resposta era "no
        # diretório de trabalho do processo" — imprevisível e, num app
        # instalado, às vezes sem permissão de escrita.
        self.output_folder_var = StringVar(value=str(default_live_sessions_dir()))

        # Calibration parameters
        self.num_aquariums_var = IntVar(value=1)
        self.animals_per_aquarium_var = IntVar(value=1)
        self.aquarium_width_var = DoubleVar(value=10.0)
        self.aquarium_height_var = DoubleVar(value=10.0)

        # Behavior analysis parameters
        sharp_turn_default = 180.0
        freeze_thresh_default = 0.5
        freeze_dur_default = 1.0
        if settings_obj and hasattr(settings_obj, "video_processing"):
            sharp_turn_default = settings_obj.video_processing.sharp_turn_threshold_deg_s
            freeze_thresh_default = settings_obj.video_processing.freezing_velocity_threshold
            freeze_dur_default = settings_obj.video_processing.freezing_min_duration_s

        self.sharp_turn_var = DoubleVar(value=sharp_turn_default)
        self.freeze_thresh_var = DoubleVar(value=freeze_thresh_default)
        self.freeze_dur_var = DoubleVar(value=freeze_dur_default)

        # Smoothing parameters
        smoothing_window_default = 5
        smoothing_polyorder_default = 2
        if settings_obj and hasattr(settings_obj, "trajectory_smoothing"):
            smoothing_window_default = settings_obj.trajectory_smoothing.window_length
            smoothing_polyorder_default = settings_obj.trajectory_smoothing.polyorder

        self.smoothing_window_var = IntVar(value=smoothing_window_default)
        self.smoothing_polyorder_var = IntVar(value=smoothing_polyorder_default)

        # Detection method parameters
        aquarium_method_default = "seg"
        animal_method_default = "seg"
        use_openvino_default = True
        if settings_obj and hasattr(settings_obj, "model_selection"):
            aquarium_method_default = settings_obj.model_selection.aquarium_method
            animal_method_default = settings_obj.model_selection.animal_method
            use_openvino_default = settings_obj.model_selection.use_openvino

        self.aquarium_method_var = StringVar(value=aquarium_method_default)
        self.animal_method_var = StringVar(value=animal_method_default)
        self.use_openvino_var = BooleanVar(value=use_openvino_default)

        super().__init__(parent, title=_("Analyze Live Camera"))

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(self)

    def body(self, master: Frame) -> Any:
        """Create dialog body."""
        # Main container with padding
        container = ttk.Frame(master, padding=10)
        container.pack(fill="both", expand=True)

        # Title
        title = Label(
            container,
            text=_("Live Camera Analysis"),
            font=("TkDefaultFont", 12, "bold"),
        )
        title.pack(pady=(0, 5))

        subtitle = Label(
            container,
            text=_("Set up and start a real-time analysis session."),
            fg="gray",
        )
        subtitle.pack(pady=(0, 15))

        # --- Camera Selection (Top) ---
        camera_frame = ttk.LabelFrame(container, text=_("Camera Selection"), padding=10)
        camera_frame.pack(fill="x", pady=(0, 10))

        # Grid for camera selection
        camera_frame.columnconfigure(1, weight=1)

        ttk.Label(camera_frame, text=_("Device:")).grid(row=0, column=0, padx=5, sticky="w")

        self.camera_combo = ttk.Combobox(
            camera_frame,
            textvariable=self.camera_selection_var,
            state="readonly",
        )
        self.camera_combo.grid(row=0, column=1, padx=5, sticky="ew")
        ToolTip(self.camera_combo, _("Select the camera for live analysis."))

        ttk.Button(camera_frame, text=_("🔍 Detect"), command=self._detect_cameras, width=10).grid(
            row=0, column=2, padx=5
        )

        self.camera_status_label = Label(camera_frame, text="", fg="gray")
        self.camera_status_label.grid(row=1, column=1, sticky="w", padx=5)

        # --- Configuration Grid (2 Columns) ---
        config_container = ttk.Frame(container)
        config_container.pack(fill="both", expand=True)
        config_container.columnconfigure(0, weight=1)
        config_container.columnconfigure(1, weight=1)

        # Left Column: Timing & Processing
        left_col = ttk.Frame(config_container)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Duration Settings
        duration_frame = ttk.LabelFrame(left_col, text=_("Timing and Processing"), padding=10)
        duration_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry
        duration_frame.columnconfigure(1, weight=0)
        duration_frame.columnconfigure(2, weight=1)

        # Duration
        ttk.Label(duration_frame, text=_("Duration (s):")).grid(
            row=0, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            _(
                "Recording/Analysis Time\n\n"
                "Sets how long the live session will last, in seconds.\n"
                "• 60s = 1 minute.\n"
                "• 300s = 5 minutes."
            ),
        ).grid(row=0, column=1, padx=2)
        duration_spin = Spinbox(
            duration_frame,
            from_=10,
            to=7200,
            textvariable=self.duration_var,
            width=8,
        )
        duration_spin.grid(row=0, column=2, padx=5, pady=2, sticky="w")

        # Quick buttons for duration
        quick_btns = ttk.Frame(duration_frame)
        quick_btns.grid(row=0, column=3, padx=5, pady=2)
        ttk.Button(quick_btns, text="1m", width=4, command=lambda: self.duration_var.set(60)).pack(
            side="left", padx=1
        )
        ttk.Button(quick_btns, text="5m", width=4, command=lambda: self.duration_var.set(300)).pack(
            side="left", padx=1
        )

        # Analysis Interval
        ttk.Label(duration_frame, text=_("Analysis interval:")).grid(
            row=1, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            _(
                "Analysis Interval (frames)\n\n"
                "Processes 1 frame out of every N frames from the camera.\n"
                "• Low values require a powerful computer.\n"
                "• Recommended for live: 1 or 2."
            ),
        ).grid(row=1, column=1, padx=2)
        analysis_spin = Spinbox(
            duration_frame,
            from_=1,
            to=60,
            textvariable=self.analysis_interval_var,
            width=8,
        )
        analysis_spin.grid(row=1, column=2, padx=5, pady=2, sticky="w")

        # Display Interval
        ttk.Label(duration_frame, text=_("Display interval:")).grid(
            row=2, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            _(
                "Display Interval (frames)\n\n"
                "How often the video on screen is refreshed.\n"
                "• Raising this helps if the interface feels slow."
            ),
        ).grid(row=2, column=1, padx=2)
        display_spin = Spinbox(
            duration_frame,
            from_=1,
            to=60,
            textvariable=self.display_interval_var,
            width=8,
        )
        display_spin.grid(row=2, column=2, padx=5, pady=2, sticky="w")

        # Right Column: Options & ID
        right_col = ttk.Frame(config_container)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Options Settings
        options_frame = ttk.LabelFrame(right_col, text=_("Session Options"), padding=10)
        options_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry
        options_frame.columnconfigure(1, weight=0)
        options_frame.columnconfigure(2, weight=1)

        # Experiment ID
        ttk.Label(options_frame, text=_("Experiment ID:")).grid(
            row=0, column=0, padx=(5, 2), pady=5, sticky="w"
        )
        create_help_label(
            options_frame,
            _(
                "Experiment Identifier\n\n"
                "Name used to organize the output files.\n"
                "• If left blank, the system generates a name from the date and time."
            ),
        ).grid(row=0, column=1, padx=2)
        id_entry = ttk.Entry(options_frame, textvariable=self.experiment_id_var)
        id_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Checkboxes
        ttk.Checkbutton(
            options_frame,
            text=_("Record video with overlay"),
            variable=self.record_video_var,
        ).grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # OpenVINO Option
        ttk.Checkbutton(
            options_frame,
            text=_("Use OpenVINO acceleration"),
            variable=self.use_openvino_var,
        ).grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # Countdown before recording. Opt-in: the countdown loop pumps the Tk
        # event loop while it waits, so it is offered rather than imposed. The
        # service side already supported it — this flow simply never sent the
        # flag, leaving working code unreachable.
        ttk.Checkbutton(
            options_frame,
            text=_("Countdown of {seconds}s before starting").format(
                seconds=self._countdown_seconds
            ),
            variable=self.use_countdown_var,
        ).grid(row=3, column=0, columnspan=3, padx=5, pady=(0, 5), sticky="w")

        # Output folder selection (mesma ideia do fluxo de projeto: o usuário
        # escolhe ONDE salvar; vazio = pasta padrão ``live_analysis_sessions/``).
        output_row = ttk.Frame(options_frame)
        output_row.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text=_("Output folder:")).grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )
        ttk.Entry(output_row, textvariable=self.output_folder_var).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Button(
            output_row, text=_("Browse..."), command=self._select_output_folder, width=11
        ).grid(row=0, column=2, padx=(5, 0))
        create_help_label(
            output_row,
            _(
                "Directory where the results will be saved.\n"
                "• If left blank, uses the default folder "
                "'~/ZebTrack/live_analysis_sessions'."
            ),
        ).grid(row=0, column=3, padx=(5, 0))

        # --- Calibration & Detection (Bottom, simplified) ---
        adv_frame = ttk.LabelFrame(
            container, text=_("Advanced AI and Setup Parameters"), padding=10
        )
        adv_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry | Label | Help | Entry
        adv_frame.columnconfigure(1, weight=0)
        adv_frame.columnconfigure(2, weight=1)
        adv_frame.columnconfigure(4, weight=0)
        adv_frame.columnconfigure(5, weight=1)

        # Row 0: Model Methods
        ttk.Label(adv_frame, text=_("Aquarium AI:")).grid(row=0, column=0, padx=(5, 2), sticky="w")
        create_help_label(
            adv_frame,
            _(
                "Segmentation or Detection model for the tank.\n"
                "• seg: slower, but outlines the edges better.\n"
                "• det: very fast."
            ),
        ).grid(row=0, column=1, padx=2)
        ttk.Combobox(
            adv_frame,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            width=8,
            state="readonly",
        ).grid(row=0, column=2, padx=5, sticky="w")

        ttk.Label(adv_frame, text=_("Fish AI:")).grid(row=0, column=3, padx=(15, 2), sticky="w")
        create_help_label(
            adv_frame,
            _("Model for the fish.\n• Use 'seg' if there is more than one fish per aquarium."),
        ).grid(row=0, column=4, padx=2)
        ttk.Combobox(
            adv_frame,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            width=8,
            state="readonly",
        ).grid(row=0, column=5, padx=5, sticky="w")

        # Row 1: Physical setup
        #
        # Nº de aquários fica DESABILITADO neste fluxo. A análise ao vivo sem
        # projeto é single-arena de ponta a ponta: a calibração ao vivo detecta
        # UM polígono, ``ProjectManager.get_zone_data()`` (o shim legado que o
        # pipeline consulta) devolve sempre ``ZoneData`` simples, e o ramo
        # multi-aquário do pipeline nunca é alcançado. Aceitar "2" aqui
        # produzia um campo validado que não mudava nada — pior que dizer que
        # a função não existe. Multi-aquário requer um projeto.
        ttk.Label(adv_frame, text=_("No. of aquariums:")).grid(
            row=1, column=0, padx=(5, 2), pady=5, sticky="w"
        )
        create_help_label(
            adv_frame,
            _(
                "Live analysis handles ONE aquarium at a time.\n"
                "For multiple aquariums, create a live project."
            ),
        ).grid(row=1, column=1, padx=2)
        Spinbox(
            adv_frame,
            from_=1,
            to=1,
            textvariable=self.num_aquariums_var,
            width=8,
            state="disabled",
        ).grid(row=1, column=2, padx=5, sticky="w")

        ttk.Label(adv_frame, text=_("Animals/aquarium:")).grid(
            row=1, column=3, padx=(15, 2), pady=5, sticky="w"
        )
        create_help_label(adv_frame, _("Number of fish inside each aquarium.")).grid(
            row=1, column=4, padx=2
        )
        Spinbox(
            adv_frame, from_=1, to=100, textvariable=self.animals_per_aquarium_var, width=8
        ).grid(row=1, column=5, padx=5, sticky="w")

        # Aviso VISÍVEL (não só no tooltip): o campo desabilitado sozinho parece
        # defeito. Vários animais no MESMO aquário continuam suportados.
        Label(
            adv_frame,
            text=_(
                "ℹ️ Live analysis covers ONE aquarium at a time. "
                "To record several aquariums at once, create a live project."
            ),
            fg="gray",
            justify="left",
        ).grid(row=2, column=0, columnspan=6, padx=5, pady=(0, 5), sticky="w")

        # --- Behavioral Analysis Widget (New) ---
        behavior_frame = ttk.LabelFrame(container, text=_("Behavioural Analysis"), padding=10)
        behavior_frame.pack(fill="x", pady=(0, 10))

        # Determine defaults
        def_thig = 1.5
        def_geo = 1.5
        def_geo_zones = 3
        def_geo_btm = 1
        def_perspective = "lateral"
        def_geotaxis_mode = "zones"

        if self.settings and hasattr(self.settings, "behavioral_analysis"):
            def_thig = self.settings.behavioral_analysis.default_thigmotaxis_distance_cm
            def_geo = self.settings.behavioral_analysis.default_geotaxis_distance_cm
            def_geo_zones = self.settings.behavioral_analysis.default_geotaxis_num_zones
            def_geo_btm = self.settings.behavioral_analysis.default_geotaxis_bottom_zones
            # Added in Phase 9
            if hasattr(self.settings.behavioral_analysis, "aquarium_perspective"):
                def_perspective = self.settings.behavioral_analysis.aquarium_perspective
            if hasattr(self.settings.behavioral_analysis, "geotaxis_mode"):
                def_geotaxis_mode = self.settings.behavioral_analysis.geotaxis_mode

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavior_frame,
            default_thigmotaxis_cm=def_thig,
            default_geotaxis_cm=def_geo,
            default_num_zones=def_geo_zones,
            default_bottom_zones=def_geo_btm,
            default_perspective=def_perspective,
            default_geotaxis_mode=def_geotaxis_mode,
            event_bus=self.event_bus,
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

        # Auto-detect on open (schedule immediately for test determinism)
        self.after(0, self._detect_cameras)

        return self.camera_combo

    def buttonbox(self) -> None:
        """Create custom button box with Start and Cancel."""
        box = Frame(self)

        Button(box, text=_("Start Analysis"), width=15, command=self.ok, default="active").pack(
            side="left", padx=5, pady=5
        )
        Button(box, text=_("Cancel"), width=10, command=self.cancel).pack(
            side="left", padx=5, pady=5
        )

        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())

        box.pack()

    def _select_output_folder(self) -> None:
        """Abre um seletor de diretório para a pasta de saída dos resultados."""
        from tkinter import filedialog

        initial = self.output_folder_var.get().strip() or None
        folder = filedialog.askdirectory(
            title=_("Select the output folder for the results"),
            initialdir=initial,
            parent=self,
        )
        if folder:
            self.output_folder_var.set(folder)

    def _detect_cameras(self) -> None:
        """Detect available cameras using WizardService."""
        self.camera_status_label.config(text=_("Detecting..."), fg="blue")
        self.update_idletasks()

        try:
            cameras = WizardService.detect_available_cameras()

            if cameras:
                # Build display names and index map
                self.camera_index_map.clear()
                display_names = []

                for cam in cameras:
                    index = cam["index"]
                    # Mesmo método de nomeação do wizard de projeto
                    # (LiveConfigStep._detect_cameras): usar o campo
                    # ``description`` que o WizardService já formata
                    # (ex.: "HD Webcam [index 0] - HD (1280x720)"). Os campos
                    # ``name``/``resolution`` não existem no dict retornado.
                    display_name = cam.get("description", _("Camera {index}").format(index=index))
                    display_names.append(display_name)
                    self.camera_index_map[display_name] = index

                self.camera_combo["values"] = display_names

                # Auto-select first camera
                if display_names and not self.camera_selection_var.get():
                    self.camera_selection_var.set(display_names[0])

                self.camera_status_label.config(
                    text=(
                        _("✓ 1 camera detected")
                        if len(cameras) == 1
                        else _("✓ {count} cameras detected").format(count=len(cameras))
                    ),
                    fg="green",
                )
            else:
                self.camera_combo["values"] = []
                self.camera_status_label.config(
                    text=_("✗ No camera detected"),
                    fg="red",
                )

        except Exception as e:
            log.error("live_analysis_dialog.camera_detection_error", error=str(e), exc_info=True)
            self.camera_status_label.config(
                text=_("✗ Error detecting cameras"),
                fg="red",
            )
            messagebox.showerror(
                _("Detection Error"),
                _("Failed to detect cameras:\n{error}").format(error=e),
                parent=self,
            )

    def _validate_output_folder(self) -> bool:
        """Ensure the chosen output folder exists and accepts writes.

        Blank stays valid: the service then applies the same default this
        dialog shows. What must not happen is discovering at the END of a
        recording that the destination was never writable.
        """
        raw = self.output_folder_var.get().strip()
        if not raw:
            return True

        folder = Path(raw)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".zebtrack_write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            log.warning(
                "live_analysis_dialog.output_folder_unusable",
                folder=str(folder),
                error=str(exc),
            )
            messagebox.showerror(
                _("Invalid Output Folder"),
                _(
                    "Cannot write to the output folder:\n{folder}\n\n{error}\n\n"
                    "Pick another folder before starting the recording."
                ).format(folder=folder, error=exc),
                parent=self,
            )
            return False

        return True

    def _validate_smoothing_parameters(self) -> bool:
        """Validate Savitzky-Golay window/order and the behavioural config.

        Extracted verbatim from ``validate`` — same checks, same messages —
        only so the caller stays under the complexity gate.
        """
        try:
            smoothing_window = int(self.smoothing_window_var.get())
            smoothing_polyorder = int(self.smoothing_polyorder_var.get())

            if smoothing_window < 3:
                raise ValueError(_("The smoothing window must be >= 3"))
            if smoothing_window % 2 == 0:
                raise ValueError(_("The smoothing window must be odd"))
            if smoothing_polyorder < 1:
                raise ValueError(_("The polynomial order must be >= 1"))
            if smoothing_polyorder >= smoothing_window:
                raise ValueError(_("The polynomial order must be smaller than the window"))

            # Validate behavioral config
            if self.behavioral_config_widget:
                is_valid, errors = self.behavioral_config_widget.validate()
                if not is_valid:
                    raise ValueError("\n".join(errors))

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                _("Invalid Parameter"),
                _("Validation error:\n{error}").format(error=e),
                parent=self,
            )
            return False

        return True

    def validate(self) -> bool:
        """Validate inputs before accepting."""
        # Check camera selection
        selected = self.camera_selection_var.get().strip()
        if not selected:
            messagebox.showwarning(
                _("No Camera Selected"),
                _("Please select a camera for the analysis."),
                parent=self,
            )
            return False

        camera_index = self.camera_index_map.get(selected)
        if camera_index is None:
            messagebox.showerror(
                _("Invalid Camera"),
                _("Camera index not found for: {camera}").format(camera=selected),
                parent=self,
            )
            return False

        # Check duration
        try:
            duration = float(self.duration_var.get())
            if duration <= 0:
                raise ValueError(_("Duration must be positive"))

            max_duration = self.settings.live_analysis.max_duration_s if self.settings else 7200.0
            if duration > max_duration:
                messagebox.showwarning(
                    _("Duration Too Long"),
                    _("Maximum allowed duration: {value}s\nAdjusting to the maximum...").format(
                        value=max_duration
                    ),
                    parent=self,
                )
                self.duration_var.set(max_duration)
                duration = max_duration

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                _("Invalid Duration"),
                _("Duration must be a positive number:\n{error}").format(error=e),
                parent=self,
            )
            return False

        # Validate the output folder BEFORE the camera opens. A folder that
        # cannot be created (or written to) used to surface only after the
        # recording had already run, with the data gone.
        if not self._validate_output_folder():
            return False

        # Validate intervals
        try:
            analysis_interval = int(self.analysis_interval_var.get())
            display_interval = int(self.display_interval_var.get())

            if analysis_interval < 1 or display_interval < 1:
                raise ValueError(_("Intervals must be >= 1"))

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                _("Invalid Interval"),
                _("Intervals must be positive whole numbers:\n{error}").format(error=e),
                parent=self,
            )
            return False

        # Validate calibration parameters
        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            aquarium_width = float(self.aquarium_width_var.get())
            aquarium_height = float(self.aquarium_height_var.get())

            if num_aquariums < 1 or animals_per_aquarium < 1:
                raise ValueError(_("The number of aquariums and animals must be >= 1"))
            if aquarium_width <= 0 or aquarium_height <= 0:
                raise ValueError(_("The aquarium dimensions must be positive"))

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                _("Invalid Calibration Parameter"),
                _("Calibration error:\n{error}").format(error=e),
                parent=self,
            )
            return False

        # Validate behavior parameters
        try:
            sharp_turn = float(self.sharp_turn_var.get())
            freeze_thresh = float(self.freeze_thresh_var.get())
            freeze_dur = float(self.freeze_dur_var.get())

            if sharp_turn < 0 or freeze_thresh < 0 or freeze_dur < 0:
                raise ValueError(_("Behavioural parameters must be non-negative"))

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                _("Invalid Behavioural Parameter"),
                _("Error in the behavioural parameters:\n{error}").format(error=e),
                parent=self,
            )
            return False

        if not self._validate_smoothing_parameters():
            return False
        return True

    def apply(self) -> None:
        """Build result dictionary and update settings."""
        selected = self.camera_selection_var.get().strip()
        camera_index = self.camera_index_map[selected]

        experiment_id = self.experiment_id_var.get().strip()
        if not experiment_id:
            from datetime import datetime

            experiment_id = f"camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        analysis_interval = int(self.analysis_interval_var.get())
        display_interval = int(self.display_interval_var.get())
        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())

        behavioral_config = {}
        if self.behavioral_config_widget:
            behavioral_config = self.behavioral_config_widget.get_values()

        # Update the shared settings object to ensure consistency in other UI tabs
        if self.settings:
            try:
                if hasattr(self.settings, "video_processing"):
                    self.settings.video_processing.processing_interval = analysis_interval
                    self.settings.video_processing.display_interval = display_interval
                    self.settings.video_processing.sharp_turn_threshold_deg_s = float(
                        self.sharp_turn_var.get()
                    )
                    self.settings.video_processing.freezing_velocity_threshold = float(
                        self.freeze_thresh_var.get()
                    )
                    self.settings.video_processing.freezing_min_duration_s = float(
                        self.freeze_dur_var.get()
                    )

                if hasattr(self.settings, "trajectory_smoothing"):
                    self.settings.trajectory_smoothing.window_length = int(
                        self.smoothing_window_var.get()
                    )
                    self.settings.trajectory_smoothing.polyorder = int(
                        self.smoothing_polyorder_var.get()
                    )

                if hasattr(self.settings, "model_selection"):
                    from typing import Literal, cast

                    self.settings.model_selection.aquarium_method = cast(
                        Literal["seg", "det"], self.aquarium_method_var.get()
                    )
                    self.settings.model_selection.animal_method = cast(
                        Literal["seg", "det"], self.animal_method_var.get()
                    )
                    self.settings.model_selection.use_openvino = bool(self.use_openvino_var.get())

                if hasattr(self.settings, "analysis_config"):
                    self.settings.analysis_config.num_aquariums = num_aquariums

                if hasattr(self.settings, "tracking"):
                    self.settings.tracking.use_single_subject_tracker = animals_per_aquarium == 1

                log.info("live_analysis_dialog.apply.settings_updated")
            except Exception as e:
                log.warning("live_analysis_dialog.apply.settings_update_failed", error=str(e))

        self.result = {
            "camera_index": camera_index,
            "duration_s": float(self.duration_var.get()),
            "analysis_interval_frames": analysis_interval,
            "display_interval_frames": display_interval,
            "record_video": bool(self.record_video_var.get()),
            "use_countdown": bool(self.use_countdown_var.get()),
            "countdown_duration_s": self._countdown_seconds,
            "experiment_id": experiment_id,
            # Calibration parameters
            "num_aquariums": num_aquariums,
            "animals_per_aquarium": animals_per_aquarium,
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            # Behavior parameters
            "sharp_turn_threshold_deg_s": float(self.sharp_turn_var.get()),
            "freezing_velocity_threshold": float(self.freeze_thresh_var.get()),
            "freezing_min_duration_s": float(self.freeze_dur_var.get()),
            # Smoothing parameters
            "smoothing_window_length": int(self.smoothing_window_var.get()),
            "smoothing_polyorder": int(self.smoothing_polyorder_var.get()),
            # Detection methods
            "aquarium_method": self.aquarium_method_var.get(),
            "animal_method": self.animal_method_var.get(),
            "use_openvino": bool(self.use_openvino_var.get()),
            "use_single_subject_tracker": animals_per_aquarium == 1,
            "behavioral_analysis": behavioral_config,
            # Pasta de saída escolhida pelo usuário (None = padrão).
            "output_folder": self.output_folder_var.get().strip() or None,
        }

        if self.result is not None:
            log.info(
                "live_analysis_dialog.configured",
                camera_index=camera_index,
                duration_s=self.result["duration_s"],
                experiment_id=experiment_id,
                num_aquariums=self.result["num_aquariums"],
                animals_per_aquarium=self.result["animals_per_aquarium"],
            )


if __name__ == "__main__":
    """Test LiveAnalysisDialog."""
    import tkinter as tk

    from zebtrack.settings import load_settings

    print("Testing LiveAnalysisDialog...")

    try:
        settings = load_settings()
        root = tk.Tk()
        root.withdraw()

        dialog = LiveAnalysisDialog(root, settings_obj=settings)

        if dialog.result:
            print("\nDialog Result:")
            for key, value in dialog.result.items():
                print(f"  {key}: {value}")
        else:
            print("\nDialog cancelled")

        root.destroy()

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    print("\nLiveAnalysisDialog test finished.")
